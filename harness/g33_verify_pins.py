"""Every figure CLAIMS.yaml pins, read back out of the bundle it names.

The registry pins figures as `path#json.pointer: value`, and until now that was
checked by a script written fresh each cycle and thrown away with the session --
so "the pinned figures still reproduce" rested on a tool nobody could re-run.
A claim whose verification cannot be repeated is a claim on trust.

Bundles live outside the repo by design, so this SKIPS what this host does not
have rather than failing: a public checkout has none at all, and that is not a
finding about the evidence.

Exact comparison. A pinned figure is a bit pattern, not an approximation --
that is the whole point of pinning it. Booleans are compared case-folded
because YAML writes `true` where Python writes `True`; the value is the same
one, and a spelling difference reported as a disagreement is a false alarm
that trains a reader to ignore the tool.
"""
import hashlib
import json
import pathlib
import re
import sys

HOME = pathlib.Path.home()
REGISTRY = pathlib.Path(__file__).resolve().parent / "evidence" / "CLAIMS.yaml"


def main() -> int:
    rows = re.findall(r"^\s+- (\S+?): (\S+)\s*$", REGISTRY.read_text(), re.M)
    ok = bad = miss = digests = 0
    for ref, want in rows:
        if ".bundles/" not in ref:
            continue
        path, _, pointer = ref.partition("#")
        f = HOME / path
        if not f.is_file():
            miss += 1
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
        for key in pointer.split("."):
            doc = doc[int(key)] if isinstance(doc, list) else doc[key]
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
          f"{bad} disagree, {miss} not on this host")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
