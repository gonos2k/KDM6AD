import unittest
import numpy as np
import replay


class ReplayTest(unittest.TestCase):
    def capture(self):
        fixed = {
            k: "a" * 64
            for k in ("cfrac", "temperature", "humidity", "surface", "geometry")
        }
        h0 = np.ones((66, 7))
        d0 = np.ones((66, 7)) * 20
        base = dict(
            bt=[250.0] * 7,
            historical_selected_direct_bt=[250.0] * 7,
            k_hydro_slot7_row45=[2.0] * 7,
            k_deff_slot7_row45=[3.0] * 7,
            k_slot_one_based=7,
            k_row_zero_based=45,
            qi_real4=1.0,
            ni_real4=2.0,
            hydro7=h0.tolist(),
            deff7=d0.tolist(),
            fixed_fields_sha256=fixed,
            quality=[0] * 7,
        )
        pairs = []
        for h in replay.HS:
            pair = {"h": h}
            for sign, label in ((1, "plus"), (-1, "minus")):
                hh = h0.copy()
                dd = d0.copy()
                hh[45, 6] += sign * h
                dd[45, 6] += sign * 2 * h
                pair[label] = dict(
                    qi_real4=float(np.float32(1 + sign * h)),
                    ni_real4=float(np.float32(2 * (1 - sign * h))),
                    hydro7=hh.tolist(),
                    deff7=dd.tolist(),
                    bt=[250 + sign * 8 * h] * 7,
                    fixed_fields_sha256=fixed,
                    quality=[0] * 7,
                )
            pairs.append(pair)
        return dict(
            schema="interior-qi-ni-normalized-v1",
            coordinate=dict(
                native_ijk_1based=[164, 242, 21],
                flat=56557,
                chunk=110,
                local_result_row=237,
                compact_profile=236,
                rttov_row_0based=45,
            ),
            channels=list(replay.CHANNELS),
            calls=dict(direct_plus_k=1, direct_only=8, replay=0),
            baseline=base,
            pairs=pairs,
        )

    def test_arithmetic(self):
        result = replay.replay(self.capture())
        for row in result:
            self.assertAlmostEqual(row["sum"][0], 8.0, places=8)
            self.assertAlmostEqual(row["fd"][0], 8.0, places=8)

    def test_rejects_off_target_and_wrong_coordinate(self):
        p = self.capture()
        p["pairs"][0]["plus"]["hydro7"][44][6] += 1
        with self.assertRaises(ValueError):
            replay.replay(p)
        p = self.capture()
        p["baseline"]["k_slot_one_based"] = 6
        with self.assertRaises(ValueError):
            replay.replay(p)

    def test_rejects_missing_optical_change_and_quality(self):
        p = self.capture()
        p["pairs"][0]["plus"]["deff7"][45][6] = 20
        with self.assertRaises(ValueError):
            replay.replay(p)
        p = self.capture()
        p["pairs"][0]["minus"]["quality"][0] = 1
        with self.assertRaises(ValueError):
            replay.replay(p)


class PacketMutationTest(unittest.TestCase):
    def test_rehashed_raw_and_receipt_mutations(self):
        import hashlib
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import verify_packet as v

        for name in (
            "results/h0_plus/out/direct/radiance.txt",
            "results/h0_plus/receipt.json",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "packet"
                shutil.copytree(v.PACKET, target)
                changed = target / name
                if name.endswith("receipt.json"):
                    receipt = json.loads(changed.read_bytes())
                    receipt["mode"] = "wrong"
                    changed.write_text(json.dumps(receipt))
                else:
                    changed.write_bytes(changed.read_bytes() + b" ")
                manifest = json.loads((target / "manifest.json").read_bytes())
                manifest[name] = hashlib.sha256(changed.read_bytes()).hexdigest()
                raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
                (target / "manifest.json").write_bytes(raw)
                with (
                    patch.object(v, "PACKET", target),
                    patch.object(v, "MANIFEST_SHA", hashlib.sha256(raw).hexdigest()),
                ):
                    with self.assertRaises(ValueError):
                        v.main()

    def test_source_mutation_rejected(self):
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import verify_packet as v

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "verify_packet.py",
                "replay.py",
                "export.py",
                "test_replay.py",
                "source_manifest.json",
            ):
                shutil.copyfile(v.ROOT / name, root / name)
            with (root / "replay.py").open("a") as f:
                f.write("# mutation\n")
            with patch.object(v, "ROOT", root), self.assertRaises(ValueError):
                v.verify_sources()


if __name__ == "__main__":
    unittest.main()
