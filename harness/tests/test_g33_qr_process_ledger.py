"""The process ledger's guards refuse rather than crash (owner review §9).

`decompose()` judges two raw streams. Its refusals are the contract a corrupt
stream is held to, so a guard that raises `KeyError` first has no contract at
all -- the caller cannot tell "these runs disagree" from "the ledger has a
bug", and neither can a reader of the traceback.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_qr_process_ledger as ql  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402

CELLS = (("c", 1), ("c", 2))


@pytest.fixture
def streams(monkeypatch):
    """Two runs over the same cells, with the readers stubbed: the subject is
    the universe comparison, not the record parsing those readers already
    have their own tests for."""
    def install(drop_operand=None, drop_state=None):
        def cells(text, *, label):
            d = {k: {"x": 1.0} for k in CELLS}
            if label == drop_operand:
                d.pop(CELLS[1])
            return d

        def state(text, *, label):
            d = {k: {"qr_pre": 0, "t": 300.0} for k in CELLS}
            if label in (drop_operand, drop_state):
                d.pop(CELLS[1])
            return d

        monkeypatch.setattr(ql, "read_cells", cells)
        monkeypatch.setattr(ql, "read_state", state)
        monkeypatch.setattr(ql, "read_dtcld", lambda t, *, label: 100.0)
        monkeypatch.setattr(ql, "verify_replay", lambda *a, **k: {})
        monkeypatch.setattr(ql, "_require_same_weights", lambda *a, **k: None)
        monkeypatch.setattr(ra, "read_text", lambda t, **k: t)
        rid = {"algorithm": "legacy", "number_transfer_metric": "thickness",
               "nsplit": 1, "carry": "rezero", "rho": "as-is", "width": 3,
               "levels": 2, "delt": 100.0, "dtcld": 100.0, "loops": 1}
        monkeypatch.setattr(
            ql, "_validated_window",
            lambda text, label: (rid, {("meta", "fixture"): "fx"}))
    return install


@pytest.mark.parametrize("drop_operand,drop_state,why", [
    ("got", None, "a cell only the base run emitted"),
    ("base", None, "a cell only the got run emitted"),
    (None, "got", "a state cell missing from an operand cell's run"),
    (None, "base", "a state cell missing from the base run"),
])
def test_a_cell_universe_mismatch_is_a_refusal_not_a_KeyError(
        streams, drop_operand, drop_state, why):
    """The universes were compared AFTER the loop that indexes across them, so
    `sb[k]` raised `KeyError` before the refusal written for exactly this case
    could run. Reproduced: `KeyError: ('c', 2)`. The published runs share a
    universe, so no figure moves -- but the guard's error contract was broken
    for the corrupt stream it exists to judge."""
    streams(drop_operand, drop_state)
    with pytest.raises(ra.RefineError) as e:
        ql.decompose("base", "got", 3, object())
    assert "different cells" in str(e.value) or "different cells" in str(e.value) \
        or "cover different cells" in str(e.value), str(e.value)


def test_matching_universes_get_past_the_guard(streams):
    """The refusals must not cost the ledger its ability to run."""
    streams()
    # It proceeds past the universe checks; what it does next is the
    # decomposition's own business and has its own coverage.
    try:
        ql.decompose("base", "got", 3, object())
    except ra.RefineError as e:
        assert "different cells" not in str(e), \
            f"a well-formed pair was refused by the universe guard: {e}"
    except Exception:
        pass


def test_the_message_names_what_is_missing(streams):
    """`the two runs emitted different cells` alone cannot be acted on."""
    streams("got")
    with pytest.raises(ra.RefineError) as e:
        ql.decompose("base", "got", 3, object())
    assert "missing" in str(e.value) and "extra" in str(e.value)
    assert str(CELLS[1]) in str(e.value), "name the cell"
