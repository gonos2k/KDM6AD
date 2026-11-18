import copy
import importlib.util
import io
import json
import unittest
import zipfile
from pathlib import Path

p = Path(__file__).with_name("validate_atomic_catalog.py")
spec = importlib.util.spec_from_file_location("atomic_catalog", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AtomicCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((m.HERE / "atomic_catalog_draft.json").read_bytes())
        cls.parent = json.loads((m.PARENT / "field_contract.json").read_bytes())
        cls.archive = (m.PARENT / "field_contract_sources.zip").read_bytes()

    def test_pinned_sources_and_blocked_inventory(self):
        result = m.validate(self.data, self.parent, self.archive)
        self.assertEqual(
            (
                result["groups"],
                result["atomic_sites_and_blockers"],
                result["new_masks"],
            ),
            (28, 191, 19),
        )
        self.assertFalse(result["capture_emitted"])

    def test_wrong_source_and_consumer_location_rejected(self):
        for side in ("source", "consumer"):
            d = copy.deepcopy(self.data)
            atom = d["atoms"][0]
            if side == "source":
                atom["source_site"]["line"] += 1
            else:
                atom["consumer"]["location"]["line"] += 1
            with (
                self.subTest(side=side),
                self.assertRaisesRegex(ValueError, "source site"),
            ):
                m.validate(d, self.parent, self.archive)

    def test_rehashed_unrelated_comment_cannot_replace_consumer(self):
        d = copy.deepcopy(self.data)
        atom = d["atoms"][0]
        source_file = atom["consumer"]["location"]["file"]
        with zipfile.ZipFile(io.BytesIO(self.archive)) as z:
            lines = z.read(source_file).decode().splitlines()
        line = next(
            i for i, value in enumerate(lines, 1) if value.lstrip().startswith("//")
        )
        atom["consumer"]["location"]["line"] = line
        atom["consumer"]["location"]["anchor"] = lines[line - 1].strip()[:12]
        with self.assertRaisesRegex(ValueError, "canonical catalog mismatch"):
            m.validate(d, self.parent, self.archive)

    def test_claimed_inline_and_applied_values_rejected(self):
        for ident in (
            "rate_min_operands.operand.cap_inline",
            "transport_qr.unresolved.realized_departure",
        ):
            d = copy.deepcopy(self.data)
            atom = next(x for x in d["atoms"] if x["atomic_id"] == ident)
            atom["binding_status"] = "READY"
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                m.validate(d, self.parent, self.archive)

    def test_missing_species_ledger_and_unreviewed_mask_rejected(self):
        d = copy.deepcopy(self.data)
        atom = next(
            x
            for x in d["atoms"]
            if x["atomic_id"] == "transport_ni.unresolved.actual_bottom_export"
        )
        atom["atomic_id"] = "wrong"
        with self.assertRaises(ValueError):
            m.validate(d, self.parent, self.archive)
        d = copy.deepcopy(self.data)
        d["proposed_masks"][0]["adapter_compatibility"] = "SUPPORTED"
        with self.assertRaisesRegex(ValueError, "mask blocked"):
            m.validate(d, self.parent, self.archive)

    def test_archive_mutation_rejected(self):
        raw = bytearray(self.archive)
        raw[len(raw) // 2] ^= 1
        with self.assertRaisesRegex(ValueError, "parent/source provenance"):
            m.validate(self.data, self.parent, bytes(raw))


if __name__ == "__main__":
    unittest.main()
