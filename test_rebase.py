# Test suite for the DAG layer and DAG-aware rebase modes.
#
# Sections covered:
#   - DAG record shape and traversal (root/commit/merge, primary, ancestors)
#   - rebase_jam:   one-shot replay producing REBASE_STEP records
#   - rebase_interactive: generator-based replay with fixup-via-send
#
# Sections 1–12 of the original test_rebase.py — and the equivalence test
# that bridges the transient and DAG paths — live in test_rebase_transient.py
# and can be dropped after merge.

from manyana import (
    current_lines,
    DAG, ROOT, COMMIT, MERGE, REBASE_STEP, BEGIN_PREFIX,
)
from rebase import rebase_jam, rebase_interactive


# ---------------------------------------------------------------------------
# DAG record shape
# ---------------------------------------------------------------------------

def test_dag_root_record_shape():
    """A root has no parents, no primary, kind=ROOT."""
    d = DAG()
    r = d.root(['A', 'B'], 'init')
    rec = d.commits[r]
    assert rec['parents'] == []
    assert rec['primary'] is None
    assert rec['kind'] == ROOT
    assert rec['message'] == 'init'
    assert current_lines(rec['state']) == ['A', 'B']


def test_dag_commit_records_single_parent():
    """A commit has one parent, primary is that parent, kind=COMMIT."""
    d = DAG()
    r = d.root(['A'])
    c = d.commit(r, ['A', 'B'])
    rec = d.commits[c]
    assert rec['parents'] == [r]
    assert rec['primary'] == r
    assert rec['kind'] == COMMIT


def test_dag_merge_records_both_parents_with_primary():
    """A merge has two parents and a primary that's one of them."""
    d = DAG()
    r = d.root(['A', 'B'])
    left = d.commit(r, ['A', 'X', 'B'])
    right = d.commit(r, ['A', 'B', 'Y'])
    m, _ = d.merge(left, right, primary=left)
    rec = d.commits[m]
    assert sorted(rec['parents']) == sorted([left, right])
    assert rec['primary'] == left
    assert rec['kind'] == MERGE


def test_dag_merge_default_primary_is_left():
    """When no primary is specified, merge defaults to the left parent."""
    d = DAG()
    r = d.root(['A'])
    left = d.commit(r, ['A', 'L'])
    right = d.commit(r, ['A', 'R'])
    m, _ = d.merge(left, right)
    assert d.commits[m]['primary'] == left


def test_dag_merge_rejects_primary_outside_parents():
    """primary must be one of the parents, not some unrelated commit."""
    d = DAG()
    r = d.root(['A'])
    left = d.commit(r, ['A', 'L'])
    right = d.commit(r, ['A', 'R'])
    unrelated = d.commit(r, ['A', 'U'])
    try:
        d.merge(left, right, primary=unrelated)
    except AssertionError:
        return
    assert False, 'merge should reject a primary that is not a parent'


def test_dag_primary_chain_is_clean_log():
    """primary_chain walks primary parents back to a root."""
    d = DAG()
    r = d.root(['A'])
    c1 = d.commit(r, ['A', 'B'])
    c2 = d.commit(c1, ['A', 'B', 'C'])
    chain = d.primary_chain(c2)
    assert chain == [c2, c1, r]


def test_dag_ancestors_include_non_primary_parents():
    """ancestors crosses every parent edge, not just primary ones."""
    d = DAG()
    r = d.root(['A'])
    left = d.commit(r, ['A', 'L'])
    right = d.commit(r, ['A', 'R'])
    m, _ = d.merge(left, right, primary=left)
    ancs = d.ancestors(m)
    # All four nodes are reachable
    assert ancs == {r, left, right, m}
    # But primary_chain only follows the primary edge
    assert d.primary_chain(m) == [m, left, r]


# ---------------------------------------------------------------------------
# Serialization — the DAG as an extended format
# ---------------------------------------------------------------------------

def test_dag_round_trips_through_dict():
    """A populated DAG survives to_dict + from_dict with structure intact."""
    d = DAG()
    r = d.root(['A', 'B'], 'init')
    left = d.commit(r, ['A', 'X', 'B'], 'add X')
    right = d.commit(r, ['A', 'B', 'Y'], 'add Y')
    m, _ = d.merge(left, right, primary=left, message='join')

    restored = DAG.from_dict(d.to_dict())
    # Same commit ids, same record contents
    assert restored.commits == d.commits
    # Traversals work on the restored DAG
    assert restored.primary_chain(m) == [m, left, r]
    assert restored.ancestors(m) == {r, left, right, m}
    # Next id is preserved so further commits don't collide
    new_id = restored.commit(m, ['A', 'X', 'B', 'Y'], 'after restore')
    assert new_id == m + 1


def test_dag_round_trips_through_json():
    """to_dict / from_dict pair survives a json.dumps / json.loads round-trip
    — including JSON's quirk of stringifying int dict keys."""
    import json
    d = DAG()
    r = d.root(['A'])
    c = d.commit(r, ['A', 'B'])
    blob = json.dumps(d.to_dict())
    restored = DAG.from_dict(json.loads(blob))
    assert restored.commits == d.commits
    assert restored.primary_chain(c) == [c, r]


# ---------------------------------------------------------------------------
# rebase_jam consuming the DAG
# ---------------------------------------------------------------------------

def test_rebase_jam_marks_steps_as_rebase_step():
    """Every replayed step has kind=REBASE_STEP, distinguishable from a plain merge."""
    d = DAG()
    r = d.root(['A', 'B'])
    v1 = d.commit(r, ['A', 'X', 'B'])
    v2 = d.commit(v1, ['A', 'X', 'Y', 'B'])
    main = d.commit(r, ['A', 'B', 'Z'])
    _, steps, _ = rebase_jam(d, [v1, v2], main)
    assert len(steps) == 2
    for s in steps:
        assert d.commits[s]['kind'] == REBASE_STEP


def test_rebase_jam_primary_chain_is_rebased_trunk():
    """Following primary parents from the tip walks the rebased trunk —
    not through any of the original local commits."""
    d = DAG()
    r = d.root(['A', 'B'])
    v1 = d.commit(r, ['A', 'X', 'B'])
    v2 = d.commit(v1, ['A', 'X', 'Y', 'B'])
    main = d.commit(r, ['A', 'B', 'Z'])
    final, steps, _ = rebase_jam(d, [v1, v2], main)

    chain = d.primary_chain(final)
    # Tip → step1 → step0 → main → root
    assert chain == [final, steps[0], main, r]
    # The original local commits are NOT on the primary chain
    assert v1 not in chain
    assert v2 not in chain


def test_rebase_jam_preserves_original_branch_in_history():
    """The original local commits are still reachable as ancestors —
    rebase records them as non-primary parents, never destroys them."""
    d = DAG()
    r = d.root(['A', 'B'])
    v1 = d.commit(r, ['A', 'X', 'B'])
    v2 = d.commit(v1, ['A', 'X', 'Y', 'B'])
    main = d.commit(r, ['A', 'B', 'Z'])
    final, _, _ = rebase_jam(d, [v1, v2], main)
    ancs = d.ancestors(final)
    assert v1 in ancs
    assert v2 in ancs
    assert main in ancs
    assert r in ancs


# ---------------------------------------------------------------------------
# rebase_interactive
# ---------------------------------------------------------------------------

def test_rebase_interactive_runs_to_completion_when_clean():
    """With pause='conflict', a clean rebase yields nothing — runs straight through."""
    d = DAG()
    r = d.root(['A', 'B'])
    v1 = d.commit(r, ['A', 'X', 'B'])               # local: insert X between A and B
    main = d.commit(r, ['A', 'B', 'Y'])              # main: insert Y at end (no conflict)

    g = rebase_interactive(d, [v1], main, pause='conflict')
    pauses = list(g)
    assert pauses == []


def test_rebase_interactive_pauses_on_conflict():
    """With pause='conflict', a conflicting rebase yields once with the annotated lines."""
    d = DAG()
    r = d.root(['A', 'B'])
    v1 = d.commit(r, ['A', 'X', 'B'])                # local: X between A and B
    main = d.commit(r, ['A', 'Y', 'B'])              # main: Y between A and B → conflict

    g = rebase_interactive(d, [v1], main, pause='conflict')
    step_id, annotated = next(g)
    assert d.commits[step_id]['kind'] == REBASE_STEP
    assert any(line.startswith(BEGIN_PREFIX) for line in annotated)
    # Calling next() again without a fixup finishes the rebase
    try:
        next(g)
        assert False, 'expected StopIteration after the only step'
    except StopIteration:
        pass


def test_rebase_interactive_pause_always_yields_every_step():
    """With pause='always', the generator yields once per local commit, conflict or not."""
    d = DAG()
    r = d.root(['A'])
    v1 = d.commit(r, ['A', 'X'])
    v2 = d.commit(v1, ['A', 'X', 'Y'])
    v3 = d.commit(v2, ['A', 'X', 'Y', 'Z'])
    main = d.commit(r, ['A', 'M'])

    g = rebase_interactive(d, [v1, v2, v3], main, pause='always')
    pauses = list(g)
    assert len(pauses) == 3


def test_rebase_interactive_send_fixup_becomes_running_base():
    """Sending a fixup commit reroutes the rebase: the next step builds
    on the fixup's state, and the fixup's primary is the conflicted step.
    Demonstrates the 'every intervening version works' workflow."""
    d = DAG()
    r = d.root(['A', 'B'])
    v1 = d.commit(r, ['A', 'X', 'B'])                # local: X between A and B
    v2 = d.commit(v1, ['A', 'X', 'B', 'Q'])          # local: Q at end
    main = d.commit(r, ['A', 'Y', 'B'])              # main: Y between A and B → conflict on step 0

    g = rebase_interactive(d, [v1, v2], main, pause='conflict')
    step0, _ = next(g)
    # User resolves the conflict by committing a clean version on top of step0
    fixup = d.commit(step0, ['A', 'X', 'Y', 'B'], 'resolve XY')
    assert d.commits[fixup]['primary'] == step0
    # Send the fixup; generator continues from there
    try:
        g.send(fixup)
    except StopIteration:
        pass
    # After the send, the next rebase step must have been built on the fixup —
    # i.e. there exists a REBASE_STEP whose primary is the fixup.
    built_on_fixup = [
        cid for cid, rec in d.commits.items()
        if rec['kind'] == REBASE_STEP and rec['primary'] == fixup
    ]
    assert len(built_on_fixup) == 1, \
        'expected exactly one rebase step built on top of the fixup'


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import inspect
    passed = 0
    failed = 0
    for name, func in sorted(globals().items()):
        if name.startswith('test') and callable(func) and not inspect.signature(func).parameters:
            try:
                func()
                passed += 1
            except Exception as e:
                print(f'FAIL: {name}: {e}')
                failed += 1
    if failed:
        print(f'\n{passed} passed, {failed} failed')
    else:
        print(f'All {passed} tests passed')
