"""Pin the import root so `pytest` works from any cwd (repo root included)
without a PYTHONPATH=kdm6_torch export — pytest imports this conftest before
collecting tests/, which makes `import kdm6` resolve to this directory."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
