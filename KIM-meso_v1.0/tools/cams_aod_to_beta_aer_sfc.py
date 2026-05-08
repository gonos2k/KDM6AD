#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import xarray as xr


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_area(area: str) -> list[str]:
    parts = [p.strip() for p in area.replace("/", ",").split(",") if p.strip()]
    if len(parts) != 4:
        die("area must be N/W/S/E (e.g., 45/110/20/150)")
    return parts


def read_ads_rc(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip()
    return data


def get_ads_client(url: str | None, key: str | None):
    try:
        import cdsapi  # type: ignore
    except Exception as exc:
        die(f"cdsapi not available: {exc}")

    ads_url = url or os.environ.get("CDSAPI_URL")
    ads_key = key or os.environ.get("CDSAPI_KEY")
    if not ads_url or not ads_key:
        for rc_path in (Path("~/.adsapirc").expanduser(),
                        Path("~/.cdsapirc").expanduser()):
            cfg = read_ads_rc(rc_path)
            ads_url = ads_url or cfg.get("url")
            ads_key = ads_key or cfg.get("key")
    if not ads_url or not ads_key:
        die("ADS credentials not set. Use --ads-url/--ads-key or set "
            "CDSAPI_URL/CDSAPI_KEY for ADS.")
    if "ads.atmosphere.copernicus.eu" not in ads_url:
        die(f"ADS URL must point to ads.atmosphere.copernicus.eu (got {ads_url})")

    return cdsapi.Client(url=ads_url, key=ads_key, quiet=True)


def download_aod(args: argparse.Namespace) -> Path:
    client = get_ads_client(args.ads_url, args.ads_key)

    year = str(args.year)
    month = f"{int(args.month):02d}"
    req = {
        "product_type": args.product_type,
        "year": year,
        "month": month,
        "variable": [args.aod_var],
        "data_format": args.data_format,
    }
    if args.product_type == "monthly_mean_by_hour_of_day":
        if not args.time:
            die("--time is required for monthly_mean_by_hour_of_day")
        req["time"] = args.time
    if args.area:
        req["area"] = parse_area(args.area)

    out_nc = Path(args.aod_file) if args.aod_file else Path(
        f"cams_aod_550_{year}{month}.nc"
    )

    if out_nc.exists() and not args.overwrite:
        die(f"{out_nc} exists (use --overwrite to replace)")

    if args.data_format == "netcdf_zip":
        zip_path = out_nc.with_suffix(".zip")
        if zip_path.exists() and not args.overwrite:
            die(f"{zip_path} exists (use --overwrite to replace)")
        client.retrieve(args.dataset, req, str(zip_path))
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = [m for m in zf.namelist() if m.endswith(".nc")]
            if not members:
                die("download zip does not contain .nc files")
            with tempfile.TemporaryDirectory() as tmpdir:
                zf.extract(members[0], path=tmpdir)
                extracted = Path(tmpdir) / members[0]
                shutil.copy2(extracted, out_nc)
        if args.keep_zip:
            pass
        else:
            zip_path.unlink(missing_ok=True)
    else:
        client.retrieve(args.dataset, req, str(out_nc))

    return out_nc


def pick_aod_var(ds: xr.Dataset, requested: str) -> str:
    if requested in ds:
        return requested

    candidates = []
    for name, var in ds.data_vars.items():
        if "aod" in name and "550" in name:
            candidates.append(name)
        else:
            long_name = str(var.attrs.get("long_name", "")).lower()
            if "aerosol optical depth" in long_name and "550" in long_name:
                candidates.append(name)

    for alt in ("aod550",):
        if alt in ds:
            candidates.insert(0, alt)

    if candidates:
        return candidates[0]

    data_vars = list(ds.data_vars.keys())
    if len(data_vars) == 1:
        return data_vars[0]

    die(f"{requested} not found in {aod_path}. Available: {data_vars}")
    return requested


def build_beta(aod_path: Path, out_path: Path, aod_var: str, height_m: float,
               time_index: int, add_time_dim: bool) -> Path:
    ds = xr.open_dataset(aod_path)
    var_name = pick_aod_var(ds, aod_var)
    aod = ds[var_name]
    if "time" in aod.dims:
        aod = aod.isel(time=time_index)
    if "valid_time" in aod.dims:
        aod = aod.isel(valid_time=time_index)

    beta = (aod / height_m).astype("float32")
    beta.name = "BETA_AER_SFC"
    beta.attrs["units"] = "1/m"
    beta.attrs["description"] = "Aerosol extinction coefficient at surface"

    if add_time_dim and "Time" not in beta.dims:
        beta = beta.expand_dims(Time=[0])

    beta.to_dataset().to_netcdf(out_path)
    return out_path


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stdout)


def regrid_to_wrf(in_beta: Path, wrfinput: Path, out_path: Path,
                  alg: str, rgr_opt: str | None) -> Path:
    cmd = [
        "ncremap",
        "-a",
        alg,
        "-v",
        "BETA_AER_SFC",
        "-d",
        str(wrfinput),
        "-i",
        str(in_beta),
        "-o",
        str(out_path),
    ]
    if rgr_opt:
        cmd.extend(["-R", rgr_opt])
    run(cmd)
    return out_path


def inject_to_wrf(regrid_path: Path, wrfinput: Path) -> None:
    cmd = ["ncks", "-A", "-v", "BETA_AER_SFC", str(regrid_path), str(wrfinput)]
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download CAMS AOD and build BETA_AER_SFC for WRF."
    )
    parser.add_argument("--download", action="store_true",
                        help="Download CAMS AOD from ADS before conversion")
    parser.add_argument("--dataset", default="cams-global-reanalysis-eac4-monthly")
    parser.add_argument("--product-type", default="monthly_mean",
                        choices=["monthly_mean", "monthly_mean_by_hour_of_day"])
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--time", help="Required for monthly_mean_by_hour_of_day (e.g., 00:00)")
    parser.add_argument("--data-format", default="netcdf_zip",
                        choices=["netcdf_zip", "grib"])
    parser.add_argument("--area", help="Subset as N/W/S/E (e.g., 45/110/20/150)")
    parser.add_argument("--ads-url", help="ADS API URL (defaults to CDSAPI_URL env)")
    parser.add_argument("--ads-key", help="ADS API key (defaults to CDSAPI_KEY env)")
    parser.add_argument("--keep-zip", action="store_true")

    parser.add_argument("--aod-file", help="Input AOD NetCDF (skip download)")
    parser.add_argument("--aod-var", default="total_aerosol_optical_depth_550nm")
    parser.add_argument("--time-index", type=int, default=0,
                        help="Time index to extract from AOD file (default 0)")
    parser.add_argument("--height-m", type=float, default=1000.0,
                        help="Scale height H for beta = AOD/H (m)")
    parser.add_argument("--beta-out", default="beta_aer_sfc_cams.nc")
    parser.add_argument("--add-time-dim", action="store_true", default=True)
    parser.add_argument("--no-add-time-dim", dest="add_time_dim", action="store_false")

    parser.add_argument("--wrfinput", help="WRF wrfinput file for regridding")
    parser.add_argument("--regrid-out", default="beta_aer_sfc_wrf.nc")
    parser.add_argument("--regrid-alg", default="esmfbilin")
    parser.add_argument("--rgr-opt", help="ncremap -R option (e.g., 'lat_nm_out=XLAT lon_nm_out=XLONG')")
    parser.add_argument("--inject", action="store_true",
                        help="Append BETA_AER_SFC into wrfinput via ncks")
    parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()

    if args.download:
        if args.year is None or args.month is None:
            die("--year and --month are required for download")
        aod_path = download_aod(args)
    else:
        if not args.aod_file:
            die("--aod-file is required when --download is not set")
        aod_path = Path(args.aod_file)

    beta_out = Path(args.beta_out)
    if beta_out.exists() and not args.overwrite:
        die(f"{beta_out} exists (use --overwrite to replace)")
    build_beta(aod_path, beta_out, args.aod_var, args.height_m,
               args.time_index, args.add_time_dim)

    if args.wrfinput:
        wrfinput = Path(args.wrfinput)
        regrid_out = Path(args.regrid_out)
        if regrid_out.exists() and not args.overwrite:
            die(f"{regrid_out} exists (use --overwrite to replace)")
        regrid_to_wrf(beta_out, wrfinput, regrid_out, args.regrid_alg, args.rgr_opt)
        if args.inject:
            inject_to_wrf(regrid_out, wrfinput)


if __name__ == "__main__":
    main()
