"""Every figure CLAIMS.yaml pins, read back out of the bundle it names.

The registry pins figures as `path#json.pointer: value`, and until now that was
checked by a script written fresh each cycle and thrown away with the session --
so "the pinned figures still reproduce" rested on a tool nobody could re-run.
A claim whose verification cannot be repeated is a claim on trust.

ONE PARSER, the evidence chain's. Three drafts of this tool read the registry
with a pattern of their own, and each one silently dropped what its pattern did
not match: rows outside `.bundles/`, then rows outside the archive-root prefix,
then rows whose value was empty or carried a space (Codex, three rounds, the
same shape each time in the fix for the last). Two readers of one document also
means two answers to "what is evidence here", which is the defect this cycle
already closed once in `dispatched_seeds`. `g33_evidence_chain.claims()` reads
the grammar, REFUSES a line it cannot parse, and needs no dependency CI does
not have -- so it is the parser, and this tool is the comparison.

MISSING EVIDENCE IS A FINDING, not a skip. A pin either reproduces, disagrees,
or is GONE, and only the first is a pass. A host with no archive at all is a
different statement from an archive with holes in it, and this says which: it
verifies nothing and reports that, rather than reporting success.

Exact comparison. A pinned figure is a bit pattern -- that is the point of
pinning it -- so the registry's own `tolerance` is honoured where it states
one and nothing is allowed to slip where it does not.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_evidence_chain as ec  # noqa: E402

HOME = pathlib.Path.home()


def _walk(doc, pointer: str):
    """The value at a dotted pointer, or `KeyError`/`IndexError` if the
    bundle does not carry it -- which is a claim the artefact does not
    support, not a reason to stop reading."""
    for key in pointer.split("."):
        doc = doc[int(key)] if isinstance(doc, list) else doc[key]
    return doc


def main() -> int:
    ok = bad = gone = digests = 0
    pinned = 0
    for claim in ec.claims():
        for path, want in claim["artifacts"].items():
            pinned += 1
            f = HOME / path
            if not f.is_file():
                gone += 1
                print(f"  GONE    {claim['id']}: {path}")
                continue
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            if got == want:
                digests += 1
            else:
                bad += 1
                print(f"  DIGEST  {claim['id']}: {path}\n"
                      f"          want {want[:16]} got {got[:16]}")
        rows = ([(v, "value") for v in claim["expected_values"]]
                + [(w, "predicate") for w in claim["expected_predicates"]])
        for row, kind in rows:
            pinned += 1
            f = HOME / row["file"]
            if not f.is_file():
                gone += 1
                print(f"  GONE    {claim['id']}: {row['file']}#{row['path']}")
                continue
            try:
                doc = _walk(json.loads(f.read_text()), row["path"])
            except (KeyError, IndexError, ValueError):
                bad += 1
                print(f"  {kind.upper():7s} {claim['id']}: {row['file']}"
                      f"#{row['path']}\n          the bundle has no such value")
                continue
            if kind == "predicate":
                same = doc is row["want"]
                want = row["want"]
            else:
                want, tol = row["value"], row.get("tolerance") or 0.0
                same = (isinstance(doc, (int, float))
                        and not isinstance(doc, bool)
                        and abs(float(doc) - float(want)) <= tol)
            if same:
                ok += 1
            else:
                bad += 1
                print(f"  {kind.upper():7s} {claim['id']}: {row['file']}"
                      f"#{row['path']}\n          want {want!r} got {doc!r}")
    print(f"{ok} figures reproduce, {digests} digests match, "
          f"{bad} disagree, {gone} gone, of {pinned} pinned")
    if not pinned:
        print("REFUSED: the registry pins no evidence at all -- either it "
              "carries none or this tool stopped recognising it")
        return 1
    if gone:
        print(f"REFUSED: {gone} pinned artefact(s) are not on this host, so "
              f"those claims were not verified. A verifier that reports "
              f"success without reading the evidence is not a verifier")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
