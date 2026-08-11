"""The claim registry is the authority on status (owner §7.5).

Findings accumulate corrections in place, so a reader cannot tell which sentence
is current — `FINDING_refinement_noise_floor_v1` still says "only the rain-chain
mstep is instrumented" while MSTEPI has been emitted since. A registry only helps
if it cannot itself drift, which is what these check.

Parsed without PyYAML: the file is a fixed, flat shape and the harness has no
third-party dependencies.
"""
import re
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
REGISTRY = EVIDENCE / "CLAIMS.yaml"
STATUSES = {"active", "superseded", "withdrawn", "hold"}


def _claims():
    """[{id, status, scope, evidence[], superseded_by?}] from the registry.

    Handles `>` block scalars: a key whose value is folded continues on the
    following more-indented lines. Dropping them silently is how `scope` came
    out empty for exactly the claims whose scope needed the most words.
    """
    out, cur, pending = [], None, None
    for line in REGISTRY.read_text().splitlines():
        if re.match(r"^  - id: ", line):
            cur = {"id": line.split("id:", 1)[1].strip(), "evidence": []}
            out.append(cur)
            pending = None
        elif cur is not None and (m := re.match(r"^    (\w+):(?: (.*))?$", line)):
            # A key with NO value -- `artifacts:` heading a list -- must still
            # END the preceding folded block. The old pattern required ": ",
            # so it did not match, `pending` stayed on `scope`, and every
            # artifact line was appended to the scope prose. It surfaced the
            # moment a claim carried both a folded scope and a pin block.
            key, val = m.group(1), (m.group(2) or "").strip()
            pending = None
            if key == "run_support":
                cur["run_support"] = [t.strip() for t in
                                      val.strip("[]").split(",") if t.strip()]
            elif key == "evidence_sha256":
                cur["evidence_sha256"] = dict(
                    t.split(":") for t in
                    re.findall(r"[\w.]+\.md:[0-9a-f]+", val))
            elif key == "evidence":
                cur["evidence"] = re.findall(r"[\w.]+\.md", val)
            elif val in (">", "|"):
                cur[key], pending = "", key      # folded: body follows
            else:
                cur[key] = val
        elif cur is not None and re.match(r"^      \S", line):
            if pending:
                cur[pending] = (cur[pending] + " " + line.strip()).strip()
            cur["evidence"] += re.findall(r"[\w.]+\.md", line)
    return out


CLAIMS = _claims()


def test_the_registry_parses_and_is_not_empty():
    assert len(CLAIMS) >= 10
    assert all(c["id"] for c in CLAIMS)


def test_claim_ids_are_unique():
    ids = [c["id"] for c in CLAIMS]
    assert len(ids) == len(set(ids))


def test_every_status_is_one_of_the_declared_states():
    for c in CLAIMS:
        assert c.get("status") in STATUSES, f"{c['id']}: {c.get('status')}"


def test_every_claim_names_evidence_that_exists():
    """A registry pointing at a document nobody wrote is worse than none."""
    for c in CLAIMS:
        assert c["evidence"], f"{c['id']} cites no evidence"
        for doc in c["evidence"]:
            assert (EVIDENCE / doc).exists(), f"{c['id']} cites missing {doc}"


def test_every_superseded_by_resolves_to_an_active_claim():
    by_id = {c["id"]: c for c in CLAIMS}
    for c in CLAIMS:
        nxt = c.get("superseded_by")
        if nxt is None:
            continue
        assert nxt in by_id, f"{c['id']} -> unknown {nxt}"
        assert by_id[nxt]["status"] == "active", \
            f"{c['id']} is superseded by {nxt}, which is not active"


def test_a_withdrawn_claim_must_say_what_replaced_it_or_stand_alone():
    """Withdrawing without a successor is allowed, but it must be deliberate:
    the pairs here all have one, and a new withdrawal without one should be a
    conscious edit to this test rather than an omission."""
    for c in CLAIMS:
        if c.get("status") == "withdrawn":
            assert "superseded_by" in c, f"{c['id']} withdrawn with no successor"


def test_every_claim_pins_the_DIGEST_of_its_evidence():
    """A registry that names a file binds nothing: the file can change under it.
    The digest is what makes a claim's evidence identifiable (owner §10.4).

    FULL sha256, not a 16-hex prefix (owner §16-6): a truncation is for display.
    An authoritative pin is the whole digest."""
    import hashlib
    for c in CLAIMS:
        pinned = c.get("evidence_sha256")
        assert pinned, f"{c['id']} pins no evidence digest"
        for doc in c["evidence"]:
            assert doc in pinned, f"{c['id']} cites {doc} without a digest"
            got = hashlib.sha256((EVIDENCE / doc).read_bytes()).hexdigest()
            assert len(pinned[doc]) == 64, (
                f"{c['id']}: {doc} is pinned by a {len(pinned[doc])}-hex "
                f"prefix. A truncation is for display; an authoritative pin is "
                f"the whole digest (owner §16-6).")
            assert pinned[doc] == got, (
                f"{c['id']}: {doc} has changed since the claim was pinned "
                f"({pinned[doc][:16]} -> {got[:16]}). Re-read the claim, "
                f"then re-pin.")


def test_every_claim_declares_a_scope():
    """The recurring defect this registry exists for is a fixture-scoped result
    quoted as a general one."""
    for c in CLAIMS:
        assert c.get("scope"), f"{c['id']} declares no scope"


@pytest.mark.parametrize("cid,expect", [
    ("G33-TURNOVER-001", "withdrawn"),      # roundoff attribution, owner P0-5
    ("G33-TURNOVER-002", "active"),
    ("G33-WATER-ORDER-001", "withdrawn"),   # mstep explains column-3 water
    ("G33-PRECIP-002", "withdrawn"),        # conservative enthalpy advantage
    # 6-14% came from an UNMATCHED contrast (qr main-chain control against an
    # ni ice-chain row) -- the weakness its own scope named. -003 runs the
    # matched contrast per row, so -002 and -004 both point there now.
    ("G33-NUMBER-002", "superseded"),
    ("G33-NUMBER-004", "withdrawn"),
    # was hold/predicted; now measured on both arms, identical to the last digit
    ("G33-NUMBER-003", "active"),
])
def test_the_corrections_this_review_required_are_recorded(cid, expect):
    got = next((c for c in CLAIMS if c["id"] == cid), None)
    assert got is not None, f"{cid} missing from the registry"
    assert got["status"] == expect


# ---- owner §10: the narrative may not drift from the registry ---------------

def test_every_finding_carries_the_registry_verdict_and_it_is_current():
    """Declaring the registry authoritative did not stop a grade table in
    FINDING_column_water_orders_v1 saying "turnover is roundoff — confirmed" for
    two commits after the registry had withdrawn exactly that. The verdict is now
    stamped into each finding, and this fails when it goes stale."""
    import sys
    sys.path.insert(0, str(EVIDENCE.parent))
    import g33_claim_header as ch
    assert ch.stamp(check=True) == 0, "run harness/g33_claim_header.py"


def test_the_conservative_arm_is_measured_not_predicted():
    """It stood as predicted/unmeasured until the overlay gained per-algorithm
    anchors; the conservative update statements differ, so the legacy anchors did
    not exist in it (owner §11)."""
    c = next(c for c in CLAIMS if c["id"] == "G33-NUMBER-003")
    assert c["status"] == "active" and c["grade"] == "confirmed"
    assert "measurement" in c["basis"]


def test_a_withdrawn_claim_is_superseded_by_the_answer_to_ITS_question():
    """G33-NUMBER-006 (ice closure measures the ice defect) pointed at the
    MAIN-chain result. The claim that actually answers it is the ice cap
    explanation (owner §9.3)."""
    by_id = {c["id"]: c for c in CLAIMS}
    assert by_id["G33-NUMBER-006"]["superseded_by"] == "G33-ICE-CAP-001"


# ---- owner P0-3: withdrawn phrasing must not survive in an ACTIVE claim ------
#
# g33_claim_header stamps status/grade/scope into each finding but never compares
# the claim's TEXT against the narrative, so authority and finding can say
# opposite things while the check stays green. That is exactly what happened:
# FINDING_metric_trajectory_split_v1 withdrew the fall-speed attribution while
# G33-NUMBER-008 still asserted it, and the registry is the authority.
#
# A general text-vs-narrative comparison is not automatable. This is narrower and
# catches the observed failure: a phrase a finding has WITHDRAWN must not appear
# in the text of any claim that is still active.

WITHDRAWN_PHRASES = {
    # withdrawn by FINDING_metric_trajectory_split_v1 (owner §7)
    "effect of density on the fall speed":
        "the departure is the measured trajectory term, not a fall-speed effect",
    # downgraded by the control's own tolerance_basis field (owner §6)
    "gamma_n roundoff bound":
        "gamma_n is a screening threshold, not a roundoff certificate",
    "roundoff certificate":
        "the tolerance is explicitly NOT a certificate",
    # withdrawn by FINDING_metric_trajectory_split_v1 (owner §8): only the DIRECT
    # metric term is magnitude-independent; the total residual is
    # magnitude-sensitive through the trajectory, by up to 6.68%
    "magnitude is not what matters":
        "only the direct metric term is magnitude-independent; the total "
        "residual is magnitude-sensitive through the trajectory",
    # withdrawn by FINDING_ice_density_matrix_v1 (owner §9): fixture, driver,
    # parser, analyzer and metric definition are shared across the two chains
    "independent replication":
        "it is cross-chain/cross-species/cross-variant; the apparatus is shared",
}


def _norm_prose(text: str) -> str:
    """The one normalisation every phrase comparison in this file uses.

    Three separate axes have each defeated a literal substring test here, one
    after another, and each was found by review rather than by the check:

      whitespace   every prose field is a YAML folded block wrapped at ~76
                   chars, so a phrase straddling a break is "...fall\n  speed"
      case         the same phrase was carried as `INDEPENDENT REPLICATION` in
                   one place and `independent replication` in another
      (both)       a rewrite can change either without changing the meaning

    Defining it once, and driving the mutation test below over the cross-product
    of those axes, is the fix for the pattern rather than for one instance.
    """
    return " ".join(text.split()).casefold()


def withdrawn_phrase_violations(registry_text: str) -> list:
    """[(claim id, phrase)] for every ACTIVE claim repeating a withdrawn phrase.

    Scans the WHOLE claim block. An earlier version split at `status:` and so
    checked `text` while skipping `basis` and `scope` — claim prose a reader
    treats as authority just as much. It was false-green on real active claim
    text, which is why `test_the_gate_actually_FIRES` exists below.

    Matching is done on WHITESPACE-NORMALISED text. Every prose field here is a
    YAML folded block wrapped at about 76 characters, so a phrase that happens to
    straddle a line break becomes "... on the fall\n      speed ..." and a
    literal substring test misses it. That is not an edge case -- it is how the
    whole registry is written, and it is the second time this exact wrapping has
    defeated a check in this file.

    A withdrawn claim MAY keep the phrase: that is its historical record, and the
    status filter is the only exemption.
    """
    out = []
    for blk in re.split(r"^  - id: ", registry_text, flags=re.M)[1:]:
        cid = blk.split("\n", 1)[0].strip()
        status = re.search(r"^    status: (\S+)", blk, re.M)
        if not status or status.group(1) != "active":
            continue
        body = _norm_prose(blk)
        out += [(cid, ph) for ph in WITHDRAWN_PHRASES
                if _norm_prose(ph) in body]
    return out


def test_no_ACTIVE_claim_repeats_a_phrase_its_finding_withdrew():
    bad = withdrawn_phrase_violations(REGISTRY.read_text())
    assert not bad, "\n".join(
        f"{cid} is active and says {ph!r} — {WITHDRAWN_PHRASES[ph]}"
        for cid, ph in bad)


@pytest.mark.parametrize("cased", [False, True], ids=["asis", "recased"])
@pytest.mark.parametrize("wrapped", [False, True], ids=["inline", "wrapped"])
@pytest.mark.parametrize("field", ["text", "basis", "scope"])
def test_the_gate_actually_FIRES_on_every_prose_field(field, wrapped, cased):
    """A gate nobody has seen fail is not evidence it works — this one WAS
    false-green on `basis` and `scope` and nothing said so. Injects a withdrawn
    phrase into each prose field of an ACTIVE claim and requires a violation."""
    phrase = next(iter(WITHDRAWN_PHRASES))
    # `wrapped` splits the phrase across a YAML folded-block line break, which is
    # how every prose field in the real registry is written.
    phrase_written = phrase.title() if cased else phrase
    if wrapped:
        head, _, tail = phrase_written.rpartition(" ")
        phrase_written = f"{head}\n      {tail}"
    reg = ("schema: 1\n\nclaims:\n"
           "  - id: G33-FAKE-001\n"
           "    text: >\n      a claim\n"
           "    status: active\n"
           "    grade: confirmed\n"
           "    basis: a basis\n"
           "    scope: a scope\n"
           "    evidence: [FINDING_x.md]\n")
    injected = reg.replace(
        {"text": "      a claim", "basis": "    basis: a basis",
         "scope": "    scope: a scope"}[field],
        {"text": f"      a claim with the {phrase_written}",
         "basis": f"    basis: a basis with the {phrase_written}",
         "scope": f"    scope: a scope with the {phrase_written}"}[field])
    assert not withdrawn_phrase_violations(reg), "the clean control must pass"
    assert withdrawn_phrase_violations(injected) == [("G33-FAKE-001", phrase)], \
        f"a withdrawn phrase in `{field}` of an active claim was not caught"


def test_a_WITHDRAWN_claim_may_keep_the_phrase():
    """Its text is the historical record of what was said; scrubbing it would
    destroy the thing the registry exists to preserve."""
    phrase = next(iter(WITHDRAWN_PHRASES))
    reg = ("schema: 1\n\nclaims:\n"
           "  - id: G33-OLD-001\n"
           f"    text: >\n      a claim with the {phrase}\n"
           "    status: withdrawn\n"
           "    superseded_by: G33-NEW-001\n"
           "    scope: a scope\n"
           "    evidence: [FINDING_x.md]\n")
    assert not withdrawn_phrase_violations(reg)


def test_the_withdrawn_lexicon_is_not_vacuous():
    """A lexicon that matches nothing anywhere would pass forever. Each entry has
    to be a phrase that WAS used, so it must still appear somewhere in the
    evidence — in a finding's correction, or in a withdrawn claim."""
    corpus = _norm_prose(REGISTRY.read_text() + "".join(
        p.read_text() for p in EVIDENCE.glob("FINDING_*.md")))
    for phrase in WITHDRAWN_PHRASES:
        assert _norm_prose(phrase) in corpus, (
            f"{phrase!r} appears nowhere — the entry is dead and the test is "
            f"asserting nothing")


def _has_artifacts(cid: str) -> bool:
    """Whether this claim's block carries an `artifacts:` list."""
    block = re.split(r"(?=\n  - id: )", REGISTRY.read_text())
    for b in block:
        if re.match(r"\n?  - id: " + re.escape(cid) + r"\s*$", b.split("\n")[0]
                    if not b.startswith("\n") else b.split("\n")[1]):
            return "\n    artifacts:" in b
    return False


#: What each kind of evidence may say about its run artifacts.
_ALLOWED = {
    "source":      {"not_applicable"},
    "measurement": {"pinned", "historical_unavailable"},
    "mixed":       {"pinned", "historical_unavailable"},
    "inference":   {"pinned", "historical_unavailable"},
}


def test_every_active_claim_declares_a_STRUCTURED_evidence_kind():
    """The previous gate found measurement claims by testing whether the word
    "measurement" appeared in the `basis` PROSE. `G33-NUMBER-008` ("three-arm
    falsification test on the forcing") and `G33-TRAJECTORY-001` ("an algebraic
    identity evaluated on six real runs") are empirical and escaped it, so they
    carried no artifact status at all and the gate passed (owner P0-E4).

    Whether a claim rests on runs is now a declared field, not a substring."""
    for c in CLAIMS:
        if c.get("status") != "active":
            continue
        kind = c.get("evidence_kind")
        assert kind in _ALLOWED, f"{c['id']}: evidence_kind is {kind!r}"
        got = c.get("artifact_status")
        assert got in _ALLOWED[kind], (
            f"{c['id']}: evidence_kind {kind} allows "
            f"{sorted(_ALLOWED[kind])}, got {got!r}")
        assert _has_artifacts(c["id"]) == (got == "pinned"), (
            f"{c['id']}: artifact_status is {got!r} but "
            f"{'pins' if _has_artifacts(c['id']) else 'pins no'} artifacts")


def test_every_active_claim_declares_STRUCTURED_run_support():
    """The escape the vocabulary must not leave open: `source` is the one kind
    that needs no run artifact, so mislabelling an empirical claim as `source`
    exempts it from the coverage requirement entirely.

    Checked STRUCTURALLY, not by scanning prose. A keyword gate flagged
    `G33-PROTOCOL-002` because its scope says it "does not re-verify physics
    already measured under schema 2" -- a NEGATIVE clause. A scan cannot read
    that, which is why the support a claim rests on is a declared field.
    """
    for c in CLAIMS:
        if c.get("status") != "active":
            continue
        kind, support = c.get("evidence_kind"), c.get("run_support")
        assert support, f"{c['id']} declares no run_support"
        if kind == "source":
            assert support == ["none"], (
                f"{c['id']} is `source` but names run support {support}. A "
                f"claim resting on runs cannot be exempt from the artifact "
                f"requirement.")
        else:
            assert support != ["none"], \
                f"{c['id']} is `{kind}` but names no run support"


def test_the_claims_that_do_not_NAME_their_runs_are_visible():
    """`unspecified` is honest and must stay countable: it marks a measurement
    claim whose scope never says which fixture produced it, so the migration
    cannot pin it without re-reading the original work."""
    unspecified = [c["id"] for c in CLAIMS if c.get("run_support") == ["unspecified"]]
    assert len(unspecified) == 4, (
        f"the unspecified set moved to {sorted(unspecified)} -- update this "
        f"deliberately, so a silent relabel is not mistaken for a migration")


def test_the_artifact_coverage_gap_is_NOT_silently_closed():
    """A guard on the guard. If this count ever reaches zero because someone
    relabelled rather than pinned, that is a different event from the migration
    actually happening, and it should be noticed."""
    unpinned = [c["id"] for c in CLAIMS
                if c.get("artifact_status") == "historical_unavailable"]
    assert unpinned, "no claims left unpinned -- was the migration done, or the " \
                     "label changed? Update this test deliberately."


def test_a_pin_block_does_not_leak_into_the_FOLDED_scope():
    """`    artifacts:` has no value after the colon, so the key pattern that
    required ": " never matched it -- the preceding folded `scope:` stayed open
    and swallowed every artifact line into the prose. It surfaced the moment a
    claim carried both a folded scope and a pin block, and it reached the
    generated finding tables."""
    for c in CLAIMS:
        scope = str(c.get("scope", ""))
        assert "manifest.json" not in scope, \
            f"{c['id']}: an artifact line leaked into the scope prose"
        assert "kdm6ad-g33m" not in scope, f"{c['id']}: same"


def test_the_claims_pinned_to_a_RERUN_are_the_ones_that_reproduced():
    """Migration is only safe where the figure survives. Each of these was
    re-run under the current producer and its published numbers reproduced
    EXACTLY, so pinning corrects nothing -- it makes the run reachable."""
    pinned = {c["id"] for c in CLAIMS if c.get("artifact_status") == "pinned"}
    assert {"G33-NUMBER-003", "G33-MAGNITUDE-002", "G33-ENTHALPY-003",
            "G33-ICE-CAP-001"} <= pinned


def test_every_PINNED_claim_binds_its_HEADLINE_figures():
    """Coverage, not just capability. `expected_values` existed but only
    G33-NUMBER-003 used it, so the other three pinned claims reached their
    exact bundle and analysis file while their published numbers were still
    unchecked (owner §9)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_evidence_chain as ec
    bound = {c["id"] for c in ec.claims() if c["expected_values"]}
    pinned = {c["id"] for c in CLAIMS if c.get("artifact_status") == "pinned"}
    missing = {p for p in pinned if p not in bound} - {"G33-TURNOVER-002"}
    assert not missing, (
        f"pinned but no figure bound to a JSON path: {sorted(missing)}")
    assert {"G33-NUMBER-003", "G33-MAGNITUDE-002", "G33-ICE-CAP-001",
            "G33-ENTHALPY-003"} <= bound


def test_G33_BASIS_005_binds_BOTH_SIDES_of_each_comparison():
    """The claim is that ONE immutable layer mass is shared by every analyzer,
    so the figures are pairs: a `cap_interface` value against the `dual_ledger`
    physical residual for the same species and column. Binding only one side
    would pin a number; binding both pins the assertion."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_evidence_chain as ec

    claim = next(c for c in ec.claims() if c["id"] == "G33-BASIS-005")
    files = [Path(w["file"]).name for w in claim["expected_values"]]
    assert files.count("n12.rezero.cap_interface.json") == 3
    assert files.count("n12.rezero.dual_ledger.json") == 3, (
        "each cap_interface figure needs its dual_ledger counterpart, or the "
        "pin does not test the claim")


def test_no_unquoted_scalar_CONTAINS_a_colon_space():
    """The exact invalidity that shipped, checked WITHOUT pyyaml.

    An unquoted YAML scalar cannot contain ": ". The pyyaml test below is the
    real check, but it `importorskip`s, and CI installs only numpy and pytest
    -- so the gate that exists to keep this file parseable silently did not run
    where it matters (Codex). CI now installs pyyaml AND this runs everywhere,
    because a regression gate that can vanish is not a gate.
    """
    offenders = []
    for n, line in enumerate(REGISTRY.read_text().splitlines(), 1):
        m = re.match(r'^\s*[\w-]+: (?![\'">|])(.*)$', line)
        if m and ": " in m.group(1):
            offenders.append(f"{n}: {line.strip()[:70]}")
    assert not offenders, (
        "unquoted scalars containing ': ' -- fold them with `>`:\n  "
        + "\n  ".join(offenders))


def test_CLAIMS_yaml_is_actually_YAML():
    """The file is consumed by a hand-written regex parser, so nothing ever
    checked it against a real YAML reader -- and a `migration_blocker` value
    containing ": " made it unparseable while every test stayed green (Codex).
    An unquoted scalar cannot contain ": "; long text must be folded."""
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(REGISTRY.read_text())
    assert isinstance(doc, dict) and doc.get("claims"), "no claims parsed"
    assert len(doc["claims"]) == len(CLAIMS), (
        f"the YAML reader sees {len(doc['claims'])} claims and the regex "
        f"parser {len(CLAIMS)} -- the two disagree about the file")


def test_the_two_readers_AGREE_on_every_migration_blocker():
    """A folded value continues on the lines below it. Reading only the first
    line captured the `>` itself: truthy, so the field looked present while
    saying nothing, and the closeout printed a blocker with no reason."""
    yaml = pytest.importorskip("yaml")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_evidence_chain as ec

    doc = yaml.safe_load(REGISTRY.read_text())
    truth = {c["id"]: " ".join(str(c.get("migration_blocker", "")).split())
             for c in doc["claims"]}
    mine = {c["id"]: " ".join(c.get("migration_blocker", "").split())
            for c in ec.claims()}
    named = {k for k, v in truth.items() if v}
    assert named, "no claim records a blocker -- this check would be vacuous"
    for cid in named:
        assert mine[cid] == truth[cid], (
            f"{cid}: regex parser read {mine[cid]!r}, YAML says {truth[cid]!r}")


def test_G33_TRAJECTORY_001_binds_the_DECOMPOSED_term_not_the_total():
    """The claim decomposes R = metric + trajectory and says "the entire
    departure is the TRAJECTORY response, measured at 1.04%/0.81% ... of the
    metric term". An earlier binding took `actual_over_baseline` -- the TOTAL --
    and computed departures by hand to justify it, while the artifact stores
    `trajectory_over_metric` outright (Codex).

    Having to do arithmetic to defend a binding is the signal that the wrong
    field was chosen: the artifact states the quantity a claim names, or the
    claim is citing something the run did not measure."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_evidence_chain as ec

    claim = next(c for c in ec.claims() if c["id"] == "G33-TRAJECTORY-001")
    paths = [w["path"] for w in claim["expected_values"]]
    assert paths, "nothing bound -- this check would be vacuous"
    assert not [p for p in paths if "actual_over_baseline" in p], \
        "the TOTAL is bound for a claim about the decomposed trajectory term"
    assert sum("trajectory_over_metric" in p for p in paths) >= 5
    assert sum("metric_over_baseline" in p for p in paths) >= 5, \
        "the 'metric term is EXACTLY -1/+2' figures must be bound too"
    assert len(paths) >= 15, (
        f"only {len(paths)} figures bound; the text publishes the trajectory "
        f"percentages, the exact metric ratios, the offset ratios and the "
        f"f32-roundoff twelfth")


def _chain():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_evidence_chain as ec
    return ec


def test_TRAJECTORY_001_binds_EVERY_ratio_its_counts_range_over():
    """The structural half, which needs NO artifact and so never skips.

    A claim stating a COUNT over a family of artifact values must bind every
    member of that family, or the count is unchecked. The previous version of
    this guard called `pytest.skip` when the bundle was absent, so on any host
    without it the anti-partial-binding regression passed having checked
    nothing -- fail-open exactly where partial binding would go unnoticed
    (Codex). The bound PATHS are in the registry, so this part is checkable
    anywhere."""
    from pathlib import PurePosixPath
    ec = _chain()
    claim = next(c for c in ec.claims() if c["id"] == "G33-TRAJECTORY-001")

    pinned_dirs = {str(PurePosixPath(f).parent) for f in claim["artifacts"]
                   if f.endswith("manifest.json")}
    assert len(pinned_dirs) == 1, pinned_dirs
    artifact = f"{next(iter(pinned_dirs))}/n12.rezero.metric_trajectory.json"

    ARMS = (("inverted", (1, 2)), ("offset+", (1, 2)), ("offset-", (1, 2, 3)),
            ("uniform", (1, 2, 3)), ("x2", (1, 2, 3)))
    ratios = {f"arms.{a}.{i}.metric_over_baseline" for a, cs in ARMS for i in cs}
    headline = {f"arms.{a}.{i}.trajectory_over_metric"
                for a, cs in ARMS if a in ("inverted", "x2") for i in cs}
    offsets = {f"arms.{a}.{i}.trajectory_over_metric"
               for a, cs in ARMS if a.startswith("offset") for i in cs}
    assert (len(ratios), len(headline), len(offsets)) == (13, 5, 5)

    # (file, path) pairs over the claim's COMPLETE binding list. Filtering
    # `bound` to the metric_trajectory artifact first made the equality exact
    # only over a subset, so an extra binding against another file in the same
    # pinned bundle passed unnoticed (Codex). Comparing everything also
    # subsumes the separate out-of-bundle check.
    required = {(artifact, q) for q in ratios | headline | offsets}
    pairs = [(w["file"], w["path"]) for w in claim["expected_values"]]
    bound = set(pairs)
    # A set collapses duplicates, so the same (file, path) bound TWICE with
    # different values satisfied the equality while one of the two carried a
    # wrong number (Codex). Compare the counts as well as the contents.
    assert len(pairs) == len(bound), (
        f"duplicate bindings: "
        f"{sorted({p for p in pairs if pairs.count(p) > 1})}")
    assert required == bound, (
        f"the binding must be exactly what the text's figures and counts range "
        f"over.\n  missing: {sorted(required - bound)}"
        f"\n  unexpected: {sorted(bound - required)}")


def test_TRAJECTORY_001s_counted_claims_are_CHECKED_not_asserted():
    """A partial binding let two wrong numbers pass as verified.

    The text said "11 of 12 metric ratios bit-exact, the twelfth 5.8e-7" and
    "the 2.25-6.68% it moves under an offset". The pinned run carries THIRTEEN
    metric ratios of which TWELVE are bit-exact, and the offset-arm trajectory
    ratios run 2.20-6.68%, not 2.25-6.68%. Both are corrected in the text and
    every ratio is bound, so the counts are now checked by the artifact rather
    than asserted beside it."""
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_evidence_chain as ec

    claim = next(c for c in ec.claims() if c["id"] == "G33-TRAJECTORY-001")
    art = next(f for f in claim["artifacts"] if f.endswith("manifest.json"))
    bundle = (ec.HOME / art).parent
    af = bundle / "n12.rezero.metric_trajectory.json"
    if not af.is_file():
        # Only the RECOMPUTATION needs the artifact; the structural half runs
        # everywhere, above.
        pytest.skip("bundle not on this host -- structural half runs regardless")

    flat = ec.flatten(json.loads(af.read_text()))
    ratios = {k: v for k, v in flat.items()
              if k.endswith(".metric_over_baseline")}
    exact = [v for v in ratios.values() if v in (-1.0, 0.0, 1.0, 2.0)]
    assert len(ratios) == 13 and len(exact) == 12, (
        f"{len(exact)} of {len(ratios)} bit-exact; the text states twelve of "
        f"thirteen")

    offs = [v for k, v in flat.items()
            if k.endswith(".trajectory_over_metric") and "offset" in k]
    assert offs, "no offset trajectory ratios -- vacuous"
    assert round(min(offs) * 100, 2) == 2.20 and round(max(offs) * 100, 2) == 6.68

    bound = {w["path"] for w in claim["expected_values"]}
    assert set(ratios) <= bound, (
        f"metric ratios not bound: {sorted(set(ratios) - bound)} -- an unbound "
        f"ratio is one the count claim is not checked against")


def test_NO_claim_binds_the_same_file_and_path_twice():
    """General form of the same defect. Every consumer that builds a set from
    `expected_values` collapses a duplicate, so a second entry for one
    (file, path) can carry any value at all and be invisible to it -- while the
    evidence chain, which resolves each entry independently, only catches it
    where the bundle is present."""
    ec = _chain()
    seen = 0
    for c in ec.claims():
        pairs = [(w["file"], w["path"]) for w in c["expected_values"]]
        seen += len(pairs)
        dupes = {p for p in pairs if pairs.count(p) > 1}
        assert not dupes, f"{c['id']} binds these twice: {sorted(dupes)}"
    assert seen, "no bindings at all -- this check would be vacuous"
