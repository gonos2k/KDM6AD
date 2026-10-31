"""Read retained private cases and direct outputs; never call a model."""

from pathlib import Path
import hashlib
import io
import json
import tarfile
import numpy as np

HERE = Path(__file__).resolve().parent
HOST = Path("/Users/yhlee/KDM6AD-k/host/research_evidence")
ORIG = (
    HOST
    / "native_full_physics_forward_20261025/runs/native_checkpoint_direct_full_domain_v1"
)
QNC = HOST / "native_qnc_guard_control_direct_20261031/direct_full_m0_v1/control/chunks"
PILOT = HOST / "native_qi_postmicro_boundary_20261030/direct_full_m0_v1/control/chunks"
BASE = (
    HERE.parent
    / "native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz"
)
MOM = (
    HERE.parent
    / "native_qi_m0_cost_decomposition_2026-10-31/data/east_cost_moment_witness.json"
)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def js(p):
    return json.loads(p.read_bytes())


def hydro(raw):
    a = np.loadtxt(io.BytesIO(raw), ndmin=2)
    if not a.shape[1] == 8:
        raise ValueError("hydro input must have eight columns")
    return a[:, 6].tolist()


def liquid(raw):
    a = np.loadtxt(io.BytesIO(raw), ndmin=2)
    if not a.shape[1] == 8:
        raise ValueError("hydro input must have eight columns")
    return a[:, 5].tolist()


def deff(raw):
    a = np.loadtxt(io.BytesIO(raw), ndmin=2)
    if not a.shape[1] == 7:
        raise ValueError("hydro diameter input must have seven columns")
    return a[:, 6].tolist()


def fraction(raw):
    a = np.loadtxt(io.BytesIO(raw), ndmin=1)
    if not a[0] == 0:
        raise ValueError("cloud fraction overlap parameter differs")
    return a[1:].tolist()


def make():
    moments = js(MOM)
    qbinding = js(QNC.parent / "binding.json")
    if not (
        qbinding["checkpoint_sha256"]
        == moments["checkpoint_sha256"]["qnc_guard_control"]
        and (not qbinding["with_k"])
    ):
        raise ValueError("guard binding checkpoint or K mode differs")
    pbinding = js(PILOT.parent / "binding.json")
    if not (
        pbinding["checkpoint_sha256"] == moments["checkpoint_sha256"]["pilot_control"]
        and (not pbinding["with_k"])
    ):
        raise ValueError("pilot binding checkpoint or K mode differs")
    with np.load(BASE, allow_pickle=False) as z:
        obs = z["obs_bt_k"].copy()
        base = z["baseline_bt_kma_v3_0"].copy()
        mask = z["m0_mask"].copy()
    rows = []
    archives = {}
    for j in [*range(3, 12), 52]:
        flat = (j - 1) * 234 + 233
        chunk = flat // 512
        local = flat % 512
        orig = ORIG / "calls" / f"chunk_{chunk:05d}"
        qr = QNC / f"chunk_{chunk:03d}"
        pr = PILOT / f"chunk_{chunk:03d}"
        orr = js(orig / "receipt.json")
        qrr = js(qr / "result.json")
        prr = js(pr / "result.json")
        if (
            not orr["checkpoint_sha256"]
            == moments["checkpoint_sha256"]["original_control"]
        ):
            raise ValueError("original checkpoint identity differs")
        for rr, binding in (
            (qrr, QNC.parent / "binding.json"),
            (prr, PILOT.parent / "binding.json"),
        ):
            rt = rr["rttov_receipt"]
            if not (
                rr["binding_sha256"] == sha(binding.read_bytes())
                and rr["chunk"] == chunk
            ):
                raise ValueError("direct result binding or chunk differs")
            if not (
                rr["direct_calls"] == rt["direct_calls"] == 1
                and rr["K_calls"] == rt["K_calls"] == 0
                and (rt["channels"] == list(range(10, 17)))
                and (rt["mode"] == "direct")
            ):
                raise ValueError("direct result flags or channels differ")
        if not (
            orr["direct_calls"] == 1
            and orr["K_calls"] == 0
            and (orr["rttov_receipt"]["channels"] == list(range(10, 17)))
        ):
            raise ValueError("original direct flags or channels differ")
        indices = [
            orr["rttov_receipt"]["source_flat_indices"],
            qrr["rttov_receipt"]["source_flat_indices"],
            prr["rttov_receipt"]["source_flat_indices"],
        ]
        names = [f"{a.index(flat) + 1:03d}" for a in indices]
        if not (all((a.count(flat) == 1 for a in indices)) and mask[flat].all()):
            raise ValueError("profile selection or M0 support differs")
        ar = js(pr / "call_archive_receipt.json")
        archive = pr / "call.tar.gz"
        archive_bytes = archive.read_bytes()
        if not (
            sha(archive_bytes) == ar["archive_sha256"]
            and sha((pr / "result.json").read_bytes()) == ar["result_sha256"]
        ):
            raise ValueError("pilot call archive or result receipt SHA differs")
        if (
            not sha((pr / "result.npz").read_bytes())
            == ar["capture_sha256"]
            == prr["capture_sha256"]
        ):
            raise ValueError("pilot capture SHA differs")
        if (
            not sha((orig / "actual_checkpoint_direct_result.npz").read_bytes())
            == orr["capture_npz"]["sha256"]
        ):
            raise ValueError("original capture SHA differs")
        if not sha((qr / "result.npz").read_bytes()) == qrr["capture_sha256"]:
            raise ValueError("guard capture SHA differs")
        basepath = (
            ORIG
            / "preflight_cases"
            / f"chunk_{chunk:05d}"
            / "case/in/profiles"
            / names[0]
            / "atm"
        )
        qpath = qr / "call/case_direct/in/profiles" / names[1] / "atm"
        optics = []
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as t:
            for source in (basepath, qpath, None):
                opt = {}
                for name, parse in [
                    ("hydro.txt", hydro),
                    ("hydro_deff.txt", deff),
                    ("hydro_frac.txt", fraction),
                ]:
                    raw = (
                        (source / name).read_bytes()
                        if source
                        else t.extractfile(
                            f"call/case_direct/in/profiles/{names[2]}/atm/{name}"
                        ).read()
                    )
                    opt[name] = {"sha256": sha(raw), "values": parse(raw)}
                    if name == "hydro.txt":
                        opt["hydro_liquid"] = {
                            "sha256": sha(raw),
                            "values": liquid(raw),
                        }
                if not len({len(x["values"]) for x in opt.values()}) == 1:
                    raise ValueError("optical layer counts differ")
                optics.append(opt)
        with np.load(qr / "result.npz", allow_pickle=False) as z:
            qbt = z["bt"][local].tolist()
            if not (z["valid"][local].all() and (z["quality"][local] == 0).all()):
                raise ValueError("guard direct validity or quality differs")
        with np.load(pr / "result.npz", allow_pickle=False) as z:
            pbt = z["bt"][local].tolist()
            if not (z["valid"][local].all() and (z["quality"][local] == 0).all()):
                raise ValueError("pilot direct validity or quality differs")
        m = next((x for x in moments["profiles"] if x["native_ij_1based"] == [234, j]))

        def huber(x):
            return 0.5 * x * x if abs(x) <= 1 else abs(x) - 0.5

        bt = [base[flat].tolist(), qbt, pbt]
        observation = obs[flat].tolist()
        loss = [[huber(v - o) for (v, o) in zip(b, observation)] for b in bt]
        rows.append(
            {
                "i": 234,
                "j": j,
                "flat": flat,
                "chunk": chunk,
                "case_profiles_1based": names,
                "observation": observation,
                "bt": bt,
                "huber": loss,
                "changed_moment_words": m["changed_moment_words"],
                "optics": optics,
            }
        )
        archives[str(chunk)] = {
            "pilot_archive_sha256": ar["archive_sha256"],
            "pilot_result_receipt_sha256": ar["result_sha256"],
            "pilot_receipt_sha256": sha(
                (pr / "call_archive_receipt.json").read_bytes()
            ),
            "original_result_receipt_sha256": sha((orig / "receipt.json").read_bytes()),
            "qnc_result_receipt_sha256": sha((qr / "result.json").read_bytes()),
        }
    return {
        "schema": "east-optical-witness-v1",
        "cases": ["original_control", "qnc_guard_control", "pilot_control"],
        "channels": list(range(10, 17)),
        "moment_packet_sha256": sha(MOM.read_bytes()),
        "original_baseline_sha256": sha(BASE.read_bytes()),
        "checkpoint_sha256": moments["checkpoint_sha256"],
        "qnc_binding_sha256": sha((QNC.parent / "binding.json").read_bytes()),
        "pilot_binding_sha256": sha((PILOT.parent / "binding.json").read_bytes()),
        "chunk_receipts": archives,
        "profiles": rows,
    }


if __name__ == "__main__":
    (HERE / "witness.json").write_text(
        json.dumps(make(), indent=2, sort_keys=True) + "\n"
    )
