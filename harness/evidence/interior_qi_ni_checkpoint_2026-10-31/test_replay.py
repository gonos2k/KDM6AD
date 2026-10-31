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
    def test_rehashed_lock_and_attestations_rejected(self):
        import hashlib
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import verify_packet as v

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "packet"
            shutil.copytree(v.PACKET, target)
            field = "profiles/001/atm/t.txt"
            changed = {"lock.json", "results/attempt.json", "results/independent_audit.json"}
            lock_path = target / "lock.json"
            lock = json.loads(lock_path.read_bytes())
            for case in lock["cases"]:
                lock["cases"][case][field] = "0" * 64
                prefix = target / "results" / case
                attempt_path = prefix / "attempt.json"
                receipt_path = prefix / "receipt.json"
                attempt = json.loads(attempt_path.read_bytes())
                receipt = json.loads(receipt_path.read_bytes())
                attempt["input_hashes"][field] = "0" * 64
                receipt["pre_input_hashes"][field] = "0" * 64
                receipt["post_input_hashes"][field] = "0" * 64
                attempt_path.write_text(json.dumps(attempt))
                receipt_path.write_text(json.dumps(receipt))
                changed.update(
                    (str(attempt_path.relative_to(target)), str(receipt_path.relative_to(target)))
                )
            lock_path.write_text(json.dumps(lock))
            lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
            for name in ("results/attempt.json", "results/independent_audit.json"):
                path = target / name
                record = json.loads(path.read_bytes())
                record["lock_sha256"] = lock_sha
                path.write_text(json.dumps(record))
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            for name in changed:
                manifest[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
            raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            manifest_path.write_bytes(raw)
            with (
                patch.object(v, "PACKET", target),
                patch.object(v, "MANIFEST_SHA", hashlib.sha256(raw).hexdigest()),
                self.assertRaisesRegex(ValueError, "lock"),
            ):
                v.main()

    def test_locked_input_attestation_rejects_changed_and_missing_entries(self):
        import hashlib
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import verify_packet as v

        cases = (
            ("h0_plus", "profiles/001/atm/t.txt", "change"),
            ("h0_plus", "profiles/001/atm/hydro_frac.txt", "change"),
            ("h0_plus", "profiles/001/atm/t.txt", "remove"),
            ("baseline", "out/rttov_test.txt", "direct_config"),
            ("h0_plus", "out/rttov_test.txt", "combined_config"),
        )
        for case, field, action in cases:
            with self.subTest(case=case, field=field, action=action):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / "packet"
                    shutil.copytree(v.PACKET, target)
                    prefix = target / "results" / case
                    receipt_path = prefix / "receipt.json"
                    attempt_path = prefix / "attempt.json"
                    receipt = json.loads(receipt_path.read_bytes())
                    attempt = json.loads(attempt_path.read_bytes())
                    for hashes in (
                        receipt["pre_input_hashes"],
                        receipt["post_input_hashes"],
                        attempt["input_hashes"],
                    ):
                        if action == "remove":
                            del hashes[field]
                        elif action == "direct_config":
                            hashes[field] = v.DIRECT_CONFIG_SHA
                        elif action == "combined_config":
                            hashes[field] = v.COMBINED_CONFIG_SHA
                        else:
                            hashes[field] = "0" * 64
                    receipt_path.write_text(json.dumps(receipt))
                    attempt_path.write_text(json.dumps(attempt))
                    manifest_path = target / "manifest.json"
                    manifest = json.loads(manifest_path.read_bytes())
                    for path in (receipt_path, attempt_path):
                        relative = str(path.relative_to(target))
                        manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
                    manifest_path.write_bytes(raw)
                    with (
                        patch.object(v, "PACKET", target),
                        patch.object(v, "MANIFEST_SHA", hashlib.sha256(raw).hexdigest()),
                        self.assertRaisesRegex(ValueError, "locked input attestation"),
                    ):
                        v.main()

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
