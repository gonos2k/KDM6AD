"""Every figure CLAIMS.yaml pins, read back out of the bundle it names.

The registry pins figures as `path#json.pointer: value`, and until now that was
checked by a script written fresh each cycle and thrown away with the session --
so "the pinned figures still reproduce" rested on a tool nobody could re-run.
A claim whose verification cannot be repeated is a claim on trust.

MISSING EVIDENCE IS A FINDING, not a skip (Codex). The first draft counted an
unresolvable pin and reported success, and its row filter dropped pins that did
not spell `.bundles/` at all -- so renaming one archive directory took 35
figures out of the count and the tool still said everything reproduced. Both
are the campaign's oldest rule in a new place: a gate that cannot see must not
answer "no". A pin either reproduces, disagrees, or is GONE, and only the first
is a pass.

A host with no archive at all is a different statement from an archive with
holes in it, and this says which: it verifies nothing and reports that it
verified nothing, rather than reporting success.

Exact comparison. A pinned figure is a bit pattern -- that is the point of
pinning it. Booleans compare case-folded because YAML writes `true` where
Python writes `True`; the value is the same one, and a spelling difference
reported as a disagreement is a false alarm that trains a reader to ignore the
tool.
"""
import hashlib
import json
import pathlib
import re
import sys

HOME = pathlib.Path.home()
REGISTRY = pathlib.Path(__file__).resolve().parent / "evidence" / "CLAIMS.yaml"
#: The archive roots the registry pins into. A row addressing one of these is
#: EVIDENCE and must resolve; anything else is prose and is not this tool's
#: business. Matching on `.bundles/` instead made the classification depend on
#: a directory NAME, so a renamed archive silently stopped being evidence.
ARCHIVE_ROOTS = ("kdm6ad-g33m-",)


def is_evidence(ref: str) -> bool:
    return "/" in ref and ref.startswith(ARCHIVE_ROOTS)


def main() -> int:
    rows = re.findall(r"^\s+- (\S+?): (\S+)\s*$", REGISTRY.read_text(), re.M)
    pins = [(ref, want) for ref, want in rows if is_evidence(ref)]
    ok = bad = gone = digests = 0
    for ref, want in pins:
        path, _, pointer = ref.partition("#")
        f = HOME / path
        if not f.is_file():
            gone += 1
            print(f"  GONE    {ref}\n          the evidence this claim rests "
                  f"on is not on this host")
            continue
        if not pointer:                        # a whole-file digest
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            if got == want:
                digests += 1
            else:
                bad += 1
                print(f"  DIGEST  {path}\n          want {want[:16]} got {got[:16]}")
            continue
        doc = json.loads(f.read_text())
        try:
            for key in pointer.split("."):
                doc = doc[int(key)] if isinstance(doc, list) else doc[key]
        except (KeyError, IndexError, ValueError):
            bad += 1
            print(f"  FIGURE  {ref}\n          the bundle has no such value")
            continue
        if isinstance(doc, bool):
            same = want.lower() == str(doc).lower()
        elif isinstance(doc, (int, float)) and re.fullmatch(r"-?[\d.eE+-]+", want):
            same = float(doc) == float(want)
        else:
            same = str(doc) == want
        if same:
            ok += 1
        else:
            bad += 1
            print(f"  FIGURE  {ref}\n          want {want} got {doc}")
    print(f"{ok} figures reproduce, {digests} digests match, "
          f"{bad} disagree, {gone} gone, of {len(pins)} pinned")
    if not pins:
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
