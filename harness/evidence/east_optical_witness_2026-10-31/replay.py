"""Offline arithmetic and joined-moment verification; no host or RTTOV calls."""

import hashlib
import json
import math
import numpy as np
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOM = (
    HERE.parent
    / "native_qi_m0_cost_decomposition_2026-10-31/data/east_cost_moment_witness.json"
)


def check_source_manifest():
    """Validate the fixed source inventory before reading numeric evidence."""
    manifest = json.loads((HERE / "source_manifest.json").read_bytes())
    names = {
        "analyze.py",
        "crosscheck_pilot.py",
        "crosscheck_qnc.py",
        "extract.py",
        "replay.py",
        "test_witness.py",
    }
    if manifest.get("schema") != "east-optical-source-manifest-v1":
        raise ValueError("source manifest schema differs")
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict) or set(hashes) != names:
        raise ValueError("source manifest inventory differs")
    for name in sorted(names):
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"packet source SHA differs: {name}")


def verify(x):
    check_source_manifest()
    root = HERE.parents[2]
    for name, digest in {
        "harness/native_checkpoint_observation.py": "115bdf2b8db76b69852fe5262c01723d198660dc9be9f7361a0ed1023671ba14",
        "harness/native_observation_batch.py": "602ca5c676014d6f14b94682053b5ba249af3a6f0ce34e3af92e01199c51e0cb",
        "harness/run_native_candidate_observation.py": "74b2ce806988761d1e162cd432e271faa4ce4bfac10817a4810e5a70ecb16fa5",
        "oracle/kdm6/obs/native_cloud_profile.py": "2aeb687fed9f660818d76f98d1f8588e2cc21c9d20a7e471ff166a999a5d202c",
        "oracle/kdm6/obs/model_profile_builder.py": "b9264edb61f32010c025718ad59ef686746f156e2a3c011c473943fbf82788ab",
        "oracle/kdm6/obs/rttov_case_writer.py": "12d8b87282e8706d9d63d28f357d7aa247b98d7ded0a7eb30e09e40144130f9d",
        "oracle/kdm6/rttov_bridge.py": "3c61c7fa6baa21ba294b37cdc17886c0f17979ee4adfae0af7e22154af964116",
    }.items():
        if not hashlib.sha256((root / name).read_bytes()).hexdigest() == digest:
            raise ValueError(f"source SHA differs: {name}")
    if not x["schema"] == "east-optical-witness-v1":
        raise ValueError("witness schema differs")
    if not x["cases"] == ["original_control", "qnc_guard_control", "pilot_control"]:
        raise ValueError("case ordering differs")
    if not x["channels"] == list(range(10, 17)):
        raise ValueError("channel ordering differs")
    if not hashlib.sha256(MOM.read_bytes()).hexdigest() == x["moment_packet_sha256"]:
        raise ValueError("moment packet SHA differs")
    m = json.loads(MOM.read_bytes())
    if not x["checkpoint_sha256"] == m["checkpoint_sha256"]:
        raise ValueError("checkpoint identities differ")
    base_path = (
        HERE.parent
        / "native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz"
    )
    if (
        not hashlib.sha256(base_path.read_bytes()).hexdigest()
        == x["original_baseline_sha256"]
        == "c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144"
    ):
        raise ValueError("original baseline SHA differs")
    with np.load(base_path, allow_pickle=False) as z:
        baseline = z["baseline_bt_kma_v3_0"].copy()
        obs = z["obs_bt_k"].copy()
        mask = z["m0_mask"].copy()
    with np.load(
        HERE.parent / "native_qi_postmicro_direct_m0_2026-10-30/data/control.npz",
        allow_pickle=False,
    ) as z:
        pilot = z["bt_k"].copy()
    if not [p["j"] for p in x["profiles"]] == [*range(3, 12), 52]:
        raise ValueError("east profile inventory differs")

    def huber(v):
        return 0.5 * v * v if abs(v) <= 1 else abs(v) - 0.5

    total = []
    for p in x["profiles"]:
        if not (
            p["i"] == 234
            and p["flat"] == (p["j"] - 1) * 234 + 233
            and (p["chunk"] == p["flat"] // 512)
        ):
            raise ValueError("profile coordinates or chunk differ")
        if not (mask[p["flat"]].all() and p["observation"] == obs[p["flat"]].tolist()):
            raise ValueError("M0 support or observation differs")
        if not (
            p["bt"][0] == baseline[p["flat"]].tolist()
            and p["bt"][2] == pilot[p["flat"]].tolist()
        ):
            raise ValueError("original or pilot BT differs from public packet")
        prior = next(
            (r for r in m["profiles"] if r["flat_index_zero_based"] == p["flat"])
        )
        if not p["changed_moment_words"] == prior["changed_moment_words"]:
            raise ValueError("checkpoint moment words differ")
        for key in ("hydro.txt", "hydro_deff.txt", "hydro_frac.txt"):
            (a, b, c) = (o[key]["values"] for o in p["optics"])
            if not (len(a) == len(b) == len(c) == 66 and a == b):
                raise ValueError("optical row count or original/guard identity differs")
            if not all((math.isfinite(v) for values in (a, b, c) for v in values)):
                raise ValueError("optical values are not finite")
        if (
            not p["optics"][1]["hydro_frac.txt"]["values"]
            == p["optics"][2]["hydro_frac.txt"]["values"]
        ):
            raise ValueError("pilot cloud fractions differ from guard")
        for opt in p["optics"]:
            for ice, liquid, frac in zip(
                opt["hydro.txt"]["values"],
                opt["hydro_liquid"]["values"],
                opt["hydro_frac.txt"]["values"],
            ):
                if not (
                    frac in (0.0, 0.999999) and (ice + liquid > 1e-06) == (frac > 0)
                ):
                    raise ValueError("serialized cloud fraction threshold differs")
        if not p["bt"][0] == p["bt"][1]:
            raise ValueError("original and guard BTs differ")
        for bt, loss in zip(p["bt"], p["huber"]):
            if not len(bt) == len(loss) == len(p["observation"]) == 7:
                raise ValueError("channel loss dimensions differ")
            if not all(
                (huber(b - o) == v for (b, o, v) in zip(bt, p["observation"], loss))
            ):
                raise ValueError("Huber loss differs from BT and observation")
        total.append(math.fsum((a - b for (a, b) in zip(p["huber"][2], p["huber"][1]))))
        if not total[-1] > 0:
            raise ValueError("profile Huber loss did not increase")
    if not math.isclose(
        math.fsum(total) / 377342, 0.000328402829590676, rel_tol=0, abs_tol=1e-18
    ):
        raise ValueError("east fixed-M0 contribution differs")
    if (
        not hashlib.sha256(
            (json.dumps(x, indent=2, sort_keys=True) + "\n").encode()
        ).hexdigest()
        == "a7748163ccf75252ec6fa8d0b38b26973dbceb8c5d24fef537ee3db356fc0136"
    ):
        raise ValueError("witness SHA differs")
    spec = spec_from_file_location("east_analyze", HERE / "analyze.py")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not mod.analyze(x) == json.loads((HERE / "analysis.json").read_bytes()):
        raise ValueError("analysis does not reproduce witness")
    spec = spec_from_file_location("east_pilot", HERE / "crosscheck_pilot.py")
    pilot = module_from_spec(spec)
    spec.loader.exec_module(pilot)
    pilot.check(x)
    return {
        "profiles": 10,
        "global_denominator": 377342,
        "pilot_minus_qnc_contribution": math.fsum(total) / 377342,
        "model_calls": 0,
    }


if __name__ == "__main__":
    check_source_manifest()
    print(
        json.dumps(
            verify(json.loads((HERE / "witness.json").read_bytes())), sort_keys=True
        )
    )
