# Test suite for history-preserving rebase
#
# Covers: trivial cases, basic replay, rebase-vs-merge equivalence,
# conflict surfacing, complex multiplayer topologies, commutativity
# preservation, idempotency, and generation counting through rebase.

from manyana import initial_state, update_state, merge_states, current_lines
from rebase import rebase, rebase_from_edits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def lines(state):
    return current_lines(state)


def has_conflicts(steps):
    return any(step['conflicts'] for step in steps)


def conflict_lines(steps):
    """Flatten all conflict annotations across steps."""
    out = []
    for step in steps:
        out.extend(step['conflicts'])
    return out


# ---------------------------------------------------------------------------
# 1. Trivial cases
# ---------------------------------------------------------------------------

def test_rebase_no_commits():
    """Rebasing zero local commits returns the new base unchanged."""
    base = initial_state(['A', 'B'])
    final, steps = rebase([], base)
    assert final == base
    assert steps == []


def test_rebase_single_commit_no_conflict():
    """Single local commit rebased onto unchanged base."""
    base = initial_state(['A', 'B'])
    v1 = update_state(base, ['A', 'X', 'B'])
    final, steps = rebase([v1], base)
    assert lines(final) == ['A', 'X', 'B']
    assert not has_conflicts(steps)


def test_rebase_noop_same_base():
    """Rebasing onto the same base you forked from is a no-op."""
    base = initial_state(['A', 'B'])
    v1 = update_state(base, ['A', 'X', 'B'])
    v2 = update_state(v1, ['A', 'X', 'Y', 'B'])
    final, steps = rebase([v1, v2], base)
    assert lines(final) == ['A', 'X', 'Y', 'B']
    assert not has_conflicts(steps)


def test_rebase_empty_file():
    """Rebase works on empty initial state."""
    base = initial_state([])
    v1 = update_state(base, ['hello'])
    new_base = initial_state(['world'])
    final, steps = rebase([v1], new_base)
    result = lines(final)
    assert 'hello' in result
    assert 'world' in result


# ---------------------------------------------------------------------------
# 2. Basic multi-commit rebase
# ---------------------------------------------------------------------------

def test_rebase_two_commits():
    """Two local commits replayed onto an advanced base."""
    base = initial_state(['A', 'B', 'C'])
    # local branch: insert X between A and B, then Y between B and C
    v1 = update_state(base, ['A', 'X', 'B', 'C'])
    v2 = update_state(v1, ['A', 'X', 'B', 'Y', 'C'])
    # main advances: insert Z at end
    new_base = update_state(base, ['A', 'B', 'C', 'Z'])
    final, steps = rebase([v1, v2], new_base)
    result = lines(final)
    assert 'X' in result
    assert 'Y' in result
    assert 'Z' in result
    # Original lines preserved
    assert 'A' in result
    assert 'B' in result
    assert 'C' in result


def test_rebase_from_edits_convenience():
    """rebase_from_edits produces same result as manual state construction."""
    base = initial_state(['A', 'B'])
    new_base = update_state(base, ['A', 'B', 'Z'])

    # Manual way
    v1 = update_state(base, ['A', 'X', 'B'])
    v2 = update_state(v1, ['A', 'X', 'Y', 'B'])
    final_manual, _ = rebase([v1, v2], new_base)

    # Convenience way
    final_conv, _ = rebase_from_edits(base, [['A', 'X', 'B'], ['A', 'X', 'Y', 'B']], new_base)

    assert lines(final_manual) == lines(final_conv)


# ---------------------------------------------------------------------------
# 3. Rebase vs merge equivalence
# ---------------------------------------------------------------------------

def test_rebase_vs_merge_single_commit():
    """For a single commit, rebase and direct merge produce same visible lines."""
    base = initial_state(['A', 'B', 'C'])
    local = update_state(base, ['A', 'X', 'B', 'C'])
    main = update_state(base, ['A', 'B', 'C', 'Z'])

    merge_state, _ = merge_states(local, main)
    rebase_state, _ = rebase([local], main)

    assert lines(merge_state) == lines(rebase_state)


def test_rebase_vs_merge_two_commits():
    """Multi-commit rebase produces same visible lines as flat merge of final states."""
    base = initial_state(['A', 'B', 'C'])
    v1 = update_state(base, ['A', 'X', 'B', 'C'])
    v2 = update_state(v1, ['A', 'X', 'B', 'Y', 'C'])
    main = update_state(base, ['A', 'B', 'C', 'Z'])

    # Direct merge of final local state with main
    merge_state, _ = merge_states(v2, main)
    # Rebase
    rebase_state, _ = rebase([v1, v2], main)

    assert lines(merge_state) == lines(rebase_state)


def test_rebase_vs_merge_with_deletions():
    """Rebase and merge agree when local commits include deletions."""
    base = initial_state(['A', 'B', 'C', 'D'])
    v1 = update_state(base, ['A', 'C', 'D'])       # delete B
    v2 = update_state(v1, ['A', 'C'])               # delete D
    main = update_state(base, ['A', 'B', 'C', 'D', 'Z'])

    merge_state, _ = merge_states(v2, main)
    rebase_state, _ = rebase([v1, v2], main)

    assert lines(merge_state) == lines(rebase_state)


# ---------------------------------------------------------------------------
# 4. Conflict surfacing
# ---------------------------------------------------------------------------

def test_rebase_surfaces_conflicts():
    """Conflicting edits at same location produce conflict annotations."""
    base = initial_state(['A', 'B'])
    local = update_state(base, ['A', 'X', 'B'])     # insert X between A and B
    main = update_state(base, ['A', 'Y', 'B'])      # insert Y between A and B

    final, steps = rebase([local], main)
    # Both X and Y should be in the result
    result = lines(final)
    assert 'X' in result
    assert 'Y' in result
    # Conflicts should be reported
    assert has_conflicts(steps)


def test_rebase_conflict_on_deletion():
    """One side deletes, the other inserts nearby — conflict."""
    base = initial_state(['A', 'B', 'C'])
    local = update_state(base, ['A', 'X', 'B', 'C'])   # insert X
    main = update_state(base, ['A', 'C'])               # delete B

    final, steps = rebase([local], main)
    result = lines(final)
    assert 'X' in result
    # The conflict should be surfaced
    assert has_conflicts(steps)


def test_rebase_partial_conflicts():
    """First commit clean, second commit conflicts."""
    base = initial_state(['A', 'B', 'C'])
    # local commit 1: insert at end (no conflict with main's edit at start)
    v1 = update_state(base, ['A', 'B', 'C', 'Z'])
    # local commit 2: modify near A (conflicts with main)
    v2 = update_state(v1, ['X', 'A', 'B', 'C', 'Z'])
    # main: also modifies near A
    main = update_state(base, ['Y', 'A', 'B', 'C'])

    final, steps = rebase([v1, v2], main)
    result = lines(final)
    assert 'X' in result
    assert 'Y' in result
    assert 'Z' in result


# ---------------------------------------------------------------------------
# 5. Complex multiplayer scenarios
# ---------------------------------------------------------------------------

def test_two_players_rebase_onto_same_base():
    """Two players independently rebase onto the same new base → same result."""
    base = initial_state(['A', 'B', 'C'])
    main = update_state(base, ['A', 'B', 'C', 'Z'])

    # Player 1's local work
    p1 = update_state(base, ['A', 'X', 'B', 'C'])
    # Player 2's local work (same edit independently)
    p2 = update_state(base, ['A', 'X', 'B', 'C'])

    r1, _ = rebase([p1], main)
    r2, _ = rebase([p2], main)

    # Identical edits rebased onto identical base → identical result
    assert lines(r1) == lines(r2)


def test_two_players_different_edits_rebase_then_merge():
    """Two players make different edits, both rebase onto main, then merge."""
    base = initial_state(['A', 'B', 'C'])
    main = update_state(base, ['A', 'B', 'C', 'Z'])

    # Player 1: insert X near top
    p1 = update_state(base, ['X', 'A', 'B', 'C'])
    # Player 2: insert Y near bottom
    p2 = update_state(base, ['A', 'B', 'Y', 'C'])

    r1, _ = rebase([p1], main)
    r2, _ = rebase([p2], main)

    # Now merge the two rebased branches
    merged, _ = merge_states(r1, r2)
    result = lines(merged)
    assert 'X' in result
    assert 'Y' in result
    assert 'Z' in result


def test_diamond_topology():
    """
    Diamond: two branches diverge from base, both rebase onto main,
    then merge with each other.

        base ──→ main
         ├──→ p1 ──→ r1 ──┐
         └──→ p2 ──→ r2 ──→ final
    """
    base = initial_state(['A', 'B', 'C'])
    main = update_state(base, ['A', 'B', 'C', 'M'])

    p1_v1 = update_state(base, ['A', 'P1', 'B', 'C'])
    p2_v1 = update_state(base, ['A', 'B', 'P2', 'C'])

    r1, _ = rebase([p1_v1], main)
    r2, _ = rebase([p2_v1], main)

    # Both rebased branches merge cleanly
    final, _ = merge_states(r1, r2)
    result = lines(final)
    assert 'P1' in result
    assert 'P2' in result
    assert 'M' in result
    assert 'A' in result
    assert 'B' in result
    assert 'C' in result


def test_three_player_staggered_rebase():
    """
    Three players with staggered rebases:
      - P1 rebases first, merges into main
      - P2 rebases onto updated main
      - P3 rebases onto final main
    """
    base = initial_state(['A', 'B', 'C'])

    p1 = update_state(base, ['A', 'P1', 'B', 'C'])
    p2 = update_state(base, ['A', 'B', 'P2', 'C'])
    p3 = update_state(base, ['A', 'B', 'C', 'P3'])

    # P1 rebases onto base (trivial) and merges to become new main
    r1, _ = rebase([p1], base)
    main_v1, _ = merge_states(base, r1)

    # P2 rebases onto main_v1
    r2, _ = rebase([p2], main_v1)
    main_v2, _ = merge_states(main_v1, r2)

    # P3 rebases onto main_v2
    r3, _ = rebase([p3], main_v2)
    main_v3, _ = merge_states(main_v2, r3)

    result = lines(main_v3)
    assert 'P1' in result
    assert 'P2' in result
    assert 'P3' in result


def test_multiplayer_concurrent_same_region():
    """
    Three players all edit the same region concurrently, then rebase
    sequentially. The CRDT should preserve all edits deterministically.
    """
    base = initial_state(['A', 'B'])

    p1 = update_state(base, ['A', 'X', 'B'])
    p2 = update_state(base, ['A', 'Y', 'B'])
    p3 = update_state(base, ['A', 'Z', 'B'])

    # Merge p1 and p2 first
    m12, _ = merge_states(p1, p2)
    # Then merge with p3
    m123, _ = merge_states(m12, p3)

    # Alternatively: rebase p2 onto p1, then rebase p3 onto that
    r2, _ = rebase([p2], p1)
    r3, _ = rebase([p3], r2)

    # Both approaches should contain all inserted lines
    result_merge = lines(m123)
    result_rebase = lines(r3)
    assert 'X' in result_merge and 'Y' in result_merge and 'Z' in result_merge
    assert 'X' in result_rebase and 'Y' in result_rebase and 'Z' in result_rebase
    # And produce the same visible content
    assert sorted(result_merge) == sorted(result_rebase)


def test_rebase_chain():
    """
    Rebase a chain of 5 commits one at a time, verify intermediate states
    are all valid and the final result contains all edits.
    """
    base = initial_state(['line'])
    commits = []
    state = base
    for i in range(5):
        new_lines = lines(state) + [f'add{i}']
        state = update_state(state, new_lines)
        commits.append(state)

    new_base = update_state(base, ['line', 'main_edit'])

    final, steps = rebase(commits, new_base)
    result = lines(final)
    assert 'main_edit' in result
    for i in range(5):
        assert f'add{i}' in result
    assert len(steps) == 5


# ---------------------------------------------------------------------------
# 6. Commutativity preservation after rebase
# ---------------------------------------------------------------------------

def test_rebased_state_merges_commutatively():
    """A rebased state still merges commutatively with other branches."""
    base = initial_state(['A', 'B', 'C'])
    local = update_state(base, ['A', 'X', 'B', 'C'])
    main = update_state(base, ['A', 'B', 'C', 'Z'])
    other = update_state(base, ['A', 'B', 'Y', 'C'])

    rebased, _ = rebase([local], main)

    # merge(rebased, other) should equal merge(other, rebased)
    s1, c1 = merge_states(rebased, other)
    s2, c2 = merge_states(other, rebased)
    assert s1 == s2
    assert lines(s1) == lines(s2)


def test_rebase_then_merge_commutative_with_third_branch():
    """
    After rebasing, merging the rebased branch with a third branch
    is commutative in both argument order.
    """
    base = initial_state(['A', 'B'])
    p1 = update_state(base, ['A', 'X', 'B'])
    p2 = update_state(base, ['A', 'Y', 'B'])
    main = update_state(base, ['A', 'B', 'Z'])

    r1, _ = rebase([p1], main)

    s1, _ = merge_states(r1, p2)
    s2, _ = merge_states(p2, r1)
    assert s1 == s2


# ---------------------------------------------------------------------------
# 7. Idempotency
# ---------------------------------------------------------------------------

def test_rebase_idempotent():
    """Rebasing onto a base you've already incorporated is effectively a no-op."""
    base = initial_state(['A', 'B'])
    local = update_state(base, ['A', 'X', 'B'])

    # First rebase
    r1, _ = rebase([local], base)
    # Second rebase onto same base
    r2, _ = rebase([r1], base)

    assert lines(r1) == lines(r2)


def test_double_rebase_same_target():
    """Rebasing an already-rebased branch onto the same target converges."""
    base = initial_state(['A', 'B'])
    local = update_state(base, ['A', 'X', 'B'])
    main = update_state(base, ['A', 'B', 'Z'])

    r1, _ = rebase([local], main)
    r2, _ = rebase([r1], main)

    assert lines(r1) == lines(r2)


# ---------------------------------------------------------------------------
# 8. Generation counting through rebase
# ---------------------------------------------------------------------------

def test_generation_counting_survives_rebase():
    """Add/delete cycles are correctly handled through rebase."""
    base = initial_state(['A'])
    # Add X, then delete it
    v1 = update_state(base, ['X', 'A'])
    v2 = update_state(v1, ['A'])         # X deleted (count=2)
    # Main adds Y
    main = update_state(base, ['A', 'Y'])

    final, _ = rebase([v1, v2], main)
    result = lines(final)
    # X should be deleted (higher generation), Y should be present
    assert 'X' not in result
    assert 'Y' in result
    assert 'A' in result


def test_delete_on_main_survives_rebase():
    """A line deleted on main stays deleted after rebase."""
    base = initial_state(['A', 'B', 'C'])
    local = update_state(base, ['A', 'B', 'C', 'X'])   # add X
    main = update_state(base, ['A', 'C'])               # delete B

    final, _ = rebase([local], main)
    result = lines(final)
    assert 'B' not in result
    assert 'X' in result


def test_resurrection_through_rebase():
    """A line deleted then re-added (odd generation) survives rebase."""
    base = initial_state(['A'])
    v1 = update_state(base, [])          # delete A (count=2)
    v2 = update_state(v1, ['A'])         # resurrect A (count=3)
    main = update_state(base, ['A', 'Z'])

    final, _ = rebase([v1, v2], main)
    result = lines(final)
    assert 'A' in result
    assert 'Z' in result


# ---------------------------------------------------------------------------
# 9. Steps metadata
# ---------------------------------------------------------------------------

def test_steps_track_primary_ancestor():
    """Each step records the correct primary ancestor."""
    base = initial_state(['A'])
    v1 = update_state(base, ['A', 'X'])
    v2 = update_state(v1, ['A', 'X', 'Y'])
    main = update_state(base, ['A', 'Z'])

    final, steps = rebase([v1, v2], main)
    # Step 0's primary is the new base (main)
    assert steps[0]['primary'] == main
    # Step 1's primary is the result of step 0
    assert steps[1]['primary'] == steps[0]['state']


def test_steps_count_matches_commits():
    """Number of steps equals number of local commits."""
    base = initial_state(['A'])
    commits = []
    state = base
    for i in range(4):
        state = update_state(state, lines(state) + [f'L{i}'])
        commits.append(state)

    _, steps = rebase(commits, base)
    assert len(steps) == 4


# ---------------------------------------------------------------------------
# 10. Edge cases
# ---------------------------------------------------------------------------

def test_rebase_both_sides_empty():
    """Rebasing empty onto empty."""
    base = initial_state([])
    final, steps = rebase([base], base)
    assert lines(final) == []


def test_rebase_local_deletes_everything():
    """Local branch deletes all lines, rebased onto main with additions."""
    base = initial_state(['A', 'B'])
    local = update_state(base, [])
    main = update_state(base, ['A', 'B', 'C'])

    final, _ = rebase([local], main)
    result = lines(final)
    # C was added on main; A and B were deleted locally
    # The CRDT resolves: deletions win for A,B; C is new so it stays
    assert 'C' in result


def test_rebase_main_deletes_everything():
    """Main deletes all lines, local adds. Rebase surfaces conflict."""
    base = initial_state(['A', 'B'])
    local = update_state(base, ['A', 'X', 'B'])
    main = update_state(base, [])

    final, steps = rebase([local], main)
    result = lines(final)
    assert 'X' in result


# ---------------------------------------------------------------------------
# 11. Associativity violation (discovered by the Ouroboros)
# ---------------------------------------------------------------------------

def test_associativity_minimal():
    """
    MINIMAL REPRODUCTION: merge is commutative but NOT associative.

    Three states forked from the same base ['A', 'B']:
      X: insert 'x' between A and B       → ['A', 'x', 'B']
      Y: delete all, re-add reversed       → ['B', 'A']   (structurally new lines!)
      Z: delete B                          → ['A']

    Y's scorched-earth-then-rebuild creates structurally new 'A' and 'B'
    lines in the weave (different depths) that share text content with the
    originals.  merge_trees matches subtrees by text (line 226 of manyana.py:
    left_trees[pos1][0] == right_trees[pos2][0]), so these textual twins get
    paired with their structural doppelgängers.  The pairing produces
    different tree shapes depending on merge order, breaking associativity:

        (X+Y)+Z  →  ['B', 'A', 'x']       (B appears once)
        X+(Y+Z)  →  ['B', 'A', 'x', 'B']  (B appears twice!)
    """
    base = initial_state(['A', 'B'])

    x = update_state(base, ['A', 'x', 'B'])

    y1 = update_state(base, [])
    y  = update_state(y1, ['B', 'A'])

    z = update_state(base, ['A'])

    xy, _ = merge_states(x, y)
    xy_z, _ = merge_states(xy, z)

    yz, _ = merge_states(y, z)
    x_yz, _ = merge_states(x, yz)

    assert lines(xy_z) == lines(x_yz), \
        f"Associativity violated: (X+Y)+Z={lines(xy_z)}, X+(Y+Z)={lines(x_yz)}"


# ---------------------------------------------------------------------------
# 11b. Associativity stress tests — pushing at the edges
# ---------------------------------------------------------------------------

def test_associativity_four_way_all_bracketings():
    """
    Four states, all five possible binary-tree bracketings.

    Includes a scorched-earth-reverse branch (Y) and a deletion branch (Z)
    to stress tree-matching with structural doppelgängers at every grouping.
    """
    base = initial_state(['A', 'B', 'C'])

    w = update_state(base, ['A', 'w', 'B', 'C'])
    x = update_state(base, ['A', 'B', 'x', 'C'])
    y = update_state(update_state(base, []), ['C', 'B', 'A'])
    z = update_state(base, ['A', 'C'])  # delete B

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    r1 = lines(m(m(m(w, x), y), z))  # ((w+x)+y)+z
    r2 = lines(m(m(w, m(x, y)), z))  # (w+(x+y))+z
    r3 = lines(m(m(w, x), m(y, z)))  # (w+x)+(y+z)
    r4 = lines(m(w, m(m(x, y), z)))  # w+((x+y)+z)
    r5 = lines(m(w, m(x, m(y, z))))  # w+(x+(y+z))

    assert r1 == r2 == r3 == r4 == r5, \
        f"4-way associativity violated:\n  1={r1}\n  2={r2}\n  3={r3}\n  4={r4}\n  5={r5}"


def test_associativity_two_scorched_earths():
    """
    Two branches both do scorched-earth rebuilds with different line orderings.

    If text-matching can cause order-dependent tree shapes, having *two*
    competing rebuilds (not just one) is the most likely way to trigger it.
    """
    base = initial_state(['A', 'B', 'C'])

    x = update_state(base, ['A', 'X', 'B', 'C'])
    y = update_state(update_state(base, []), ['C', 'A', 'B'])
    z = update_state(update_state(base, []), ['B', 'C', 'A'])

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    r1 = lines(m(m(x, y), z))
    r2 = lines(m(x, m(y, z)))
    r3 = lines(m(m(x, z), y))

    assert r1 == r2 == r3, \
        f"Two-scorched-earth associativity violated:\n  (X+Y)+Z={r1}\n  X+(Y+Z)={r2}\n  (X+Z)+Y={r3}"


def test_associativity_high_generation_counts():
    """
    Three branches where the same line 'A' has very different generation counts.

    X: count=11 (alive, 5 add/delete cycles)
    Y: count=7  (alive, 3 cycles)
    Z: count=2  (dead, deleted once) + new line 'B'

    Stresses whether max() preserves associativity when counts span a wide range.
    """
    base = initial_state(['A'])

    x = base
    for _ in range(5):
        x = update_state(x, [])
        x = update_state(x, ['A'])

    y = base
    for _ in range(3):
        y = update_state(y, [])
        y = update_state(y, ['A'])

    z = update_state(update_state(base, ['A', 'B']), ['B'])

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    r1 = lines(m(m(x, y), z))
    r2 = lines(m(x, m(y, z)))

    assert r1 == r2, \
        f"High-gen-count associativity violated: (X+Y)+Z={r1}, X+(Y+Z)={r2}"


def test_associativity_generation_parity_battle():
    """
    Branches with the same line at different counts AND different alive/dead parity.

    W: count=4 (dead)    — deleted twice after two resurrections
    V: count=3 (alive)   — resurrected after one delete
    U: count=1 (alive)   — original base

    max(4,3)=4 (dead) vs max(3,1)=3 (alive) — the grouping determines
    which max() happens first, so if the result differs we've lost information.
    """
    base = initial_state(['A', 'B'])

    w = base
    w = update_state(w, [])
    w = update_state(w, ['A', 'B'])
    w = update_state(w, [])  # A=4, B=4: dead

    v = base
    v = update_state(v, [])
    v = update_state(v, ['A', 'B'])  # A=3, B=3: alive

    u = base  # A=1, B=1: alive

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    r1 = lines(m(m(w, v), u))
    r2 = lines(m(w, m(v, u)))

    assert r1 == r2, \
        f"Parity battle associativity violated: (W+V)+U={r1}, W+(V+U)={r2}"


def test_associativity_duplicate_line_text():
    """
    Scorched-earth rebuilds that introduce duplicate copies of a line.

    Y rebuilds with 'B' appearing twice; Z rebuilds with 'A' appearing twice.
    Tree-matching pairs on text, so duplicate text at different depths is the
    highest-risk pattern for order-dependent subtree shapes.
    """
    base = initial_state(['A', 'B', 'C'])

    x = update_state(base, ['A', 'p', 'B', 'q', 'C'])
    y = update_state(update_state(base, []), ['C', 'B', 'A', 'B'])
    z = update_state(update_state(base, []), ['A', 'C', 'A'])

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    r1 = lines(m(m(x, y), z))
    r2 = lines(m(x, m(y, z)))
    r3 = lines(m(m(x, z), y))

    assert r1 == r2 == r3, \
        f"Duplicate-text associativity violated:\n  (X+Y)+Z={r1}\n  X+(Y+Z)={r2}\n  (X+Z)+Y={r3}"


def test_associativity_self_referential_merge():
    """
    Merge result fed back as input alongside its own operands.

    If merge(X,Y) = XY, then merge(XY, X) must be associative with Y.
    This is the pattern rebase creates: each step's output becomes the next
    step's input, eventually re-merging with the original branch tip.
    """
    base = initial_state(['A', 'B'])

    x = update_state(base, ['A', 'x', 'B'])
    y = update_state(update_state(base, []), ['B', 'A'])

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    xy = m(x, y)
    r1 = lines(m(m(xy, x), y))
    r2 = lines(m(xy, m(x, y)))
    r3 = lines(m(m(xy, y), x))
    r4 = lines(m(xy, m(y, x)))

    assert r1 == r2 == r3 == r4, \
        f"Self-referential associativity violated:\n  (XY+X)+Y={r1}\n  XY+(XY)={r2}\n  (XY+Y)+X={r3}\n  XY+(Y+X)={r4}"


def test_associativity_six_branches_all_permutations():
    """
    Six diverse branches merged via fold-left in all 720 permutations.

    This is the brute-force convergence test. If any permutation of
    fold-left merge produces a different result, associativity is broken.
    Includes: insertions, deletions, scorched-earth reverse, add-then-remove
    (dead line with gen count 2), and deletion of original content.
    """
    from itertools import permutations

    base = initial_state(['A', 'B', 'C', 'D'])

    branches = [
        update_state(base, ['A', 'x1', 'B', 'C', 'D']),                       # insert
        update_state(base, ['A', 'C', 'D']),                                   # delete B
        update_state(update_state(base, []), ['D', 'C', 'B', 'A']),            # scorched + reverse
        update_state(update_state(base, ['A', 'B', 'C', 'D', 'E']),
                     ['A', 'B', 'C', 'D']),                                    # add E then remove (gen 2)
        update_state(base, ['A', 'B', 'x2', 'C', 'D']),                       # insert different spot
        update_state(base, ['B', 'C', 'D']),                                   # delete A
    ]

    def m(a, b):
        s, _ = merge_states(a, b)
        return s

    results = set()
    for perm in permutations(range(6)):
        acc = branches[perm[0]]
        for i in perm[1:]:
            acc = m(acc, branches[i])
        results.add(tuple(lines(acc)))

    assert len(results) == 1, \
        f"6-branch convergence failed: {len(results)} distinct results from 720 permutations"


# ---------------------------------------------------------------------------
# 12. The Ouroboros
# ---------------------------------------------------------------------------

def test_ouroboros():
    """
    Six developers.  One file.  Total chaos.  Eventual consistency.

    The topology (good luck drawing this on a whiteboard):

        base
        ├─→ alice:   add→delete→resurrect→edit       (4 commits, generation count 3 on a line)
        ├─→ bob:     independent identical add→delete→resurrect  (same content, different history)
        ├─→ carol:   deletes half the file, inserts a novel in the middle
        ├─→ dave:    inserts between every single line
        ├─→ eve:     reverses the original content (delete all, re-add reversed)
        └─→ frank:   does nothing, then panics and makes 5 rapid edits

    Then:
        1. alice and bob merge  (structurally identical edits, different weave histories)
        2. carol rebases onto alice⊕bob
        3. dave rebases onto carol's rebase
        4. eve merges with dave's rebase
        5. frank rebases onto eve⊕dave
        6. The final result merges with alice⊕bob  (circular dependency!)
        7. We take every intermediate artifact and merge ALL of them
           in 30 random permutations.  Every permutation must converge
           to the exact same visible lines.

    If the CRDT is sound, every single path through this insanity
    produces the same file.  If not, the universe was broken to begin with.
    """
    from itertools import permutations
    import random

    # === The primordial file ===
    base = initial_state(['alpha', 'beta', 'gamma', 'delta', 'epsilon'])

    # === Alice: add→delete→resurrect→edit (4 commits) ===
    a1 = update_state(base, ['alpha', 'ALICE', 'beta', 'gamma', 'delta', 'epsilon'])
    a2 = update_state(a1, ['alpha', 'beta', 'gamma', 'delta', 'epsilon'])           # delete ALICE (gen 2)
    a3 = update_state(a2, ['alpha', 'ALICE', 'beta', 'gamma', 'delta', 'epsilon'])  # resurrect (gen 3)
    a4 = update_state(a3, ['alpha', 'ALICE_v2', 'beta', 'gamma', 'delta', 'epsilon'])  # edit (new line replaces)

    # === Bob: independently does the same add→delete→resurrect ===
    b1 = update_state(base, ['alpha', 'ALICE', 'beta', 'gamma', 'delta', 'epsilon'])
    b2 = update_state(b1, ['alpha', 'beta', 'gamma', 'delta', 'epsilon'])           # delete (gen 2)
    b3 = update_state(b2, ['alpha', 'ALICE', 'beta', 'gamma', 'delta', 'epsilon'])  # resurrect (gen 3)

    # === Carol: deletes half, inserts a novel ===
    c1 = update_state(base, ['alpha', 'gamma', 'epsilon'])                          # delete beta, delta
    c2 = update_state(c1, ['alpha', 'CAROL_1', 'CAROL_2', 'CAROL_3', 'gamma', 'epsilon'])

    # === Dave: inserts between every original line ===
    d1 = update_state(base, ['alpha', 'd1', 'beta', 'd2', 'gamma', 'd3', 'delta', 'd4', 'epsilon'])

    # === Eve: scorched earth then rebuild reversed ===
    e1 = update_state(base, [])                                                     # delete everything
    e2 = update_state(e1, ['epsilon', 'delta', 'gamma', 'beta', 'alpha'])           # reversed (all new lines!)

    # === Frank: panic commits ===
    f1 = update_state(base, ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'FRANK'])
    f2 = update_state(f1, ['alpha', 'beta', 'gamma', 'delta', 'epsilon'])           # undo
    f3 = update_state(f2, ['FRANK_YOLO', 'alpha', 'beta', 'gamma', 'delta', 'epsilon'])
    f4 = update_state(f3, ['FRANK_YOLO', 'alpha', 'gamma', 'delta', 'epsilon'])     # delete beta
    f5 = update_state(f4, ['FRANK_YOLO', 'alpha', 'gamma', 'delta', 'epsilon', 'FRANK_FINAL'])

    # === Round 1: alice ⊕ bob (same content, different histories!) ===
    alice_bob, _ = merge_states(a4, b3)

    # === Round 2: carol rebases onto alice⊕bob ===
    carol_rebased, carol_steps = rebase([c1, c2], alice_bob)

    # === Round 3: dave rebases onto carol's rebase ===
    dave_rebased, dave_steps = rebase([d1], carol_rebased)

    # === Round 4: eve merges with dave's rebase ===
    eve_dave, _ = merge_states(e2, dave_rebased)

    # === Round 5: frank rebases onto eve⊕dave ===
    frank_rebased, frank_steps = rebase([f1, f2, f3, f4, f5], eve_dave)

    # === Round 6: the ouroboros closes — merge frank's result back with alice⊕bob ===
    ouroboros, _ = merge_states(frank_rebased, alice_bob)

    # === Sanity: the result should contain contributions from everyone ===
    final_lines = lines(ouroboros)

    # Alice's edited line or Bob's resurrected line should show up
    assert 'ALICE_v2' in final_lines or 'ALICE' in final_lines, \
        f"Neither ALICE nor ALICE_v2 survived the ouroboros: {final_lines}"
    # Carol's novel
    assert 'CAROL_1' in final_lines, f"Carol's work lost: {final_lines}"
    # Dave's insertions
    assert 'd1' in final_lines or 'd2' in final_lines, f"Dave's work lost: {final_lines}"
    # Frank's final mark
    assert 'FRANK_YOLO' in final_lines, f"Frank's YOLO lost: {final_lines}"
    assert 'FRANK_FINAL' in final_lines, f"Frank's FINAL lost: {final_lines}"

    # === The real test: eventual consistency ===
    # Gather every interesting intermediate state
    artifacts = [
        alice_bob,
        carol_rebased,
        dave_rebased,
        eve_dave,
        frank_rebased,
        ouroboros,
        a4, b3, c2, d1, e2, f5,  # raw branch tips too
    ]

    # Merge ALL artifacts together.  Do it in 30 random permutations.
    # Every single one must produce the same visible lines.
    random.seed(42)  # reproducible chaos
    canonical = None
    saw_violation = False

    for trial in range(30):
        order = list(range(len(artifacts)))
        random.shuffle(order)

        accumulated = artifacts[order[0]]
        for idx in order[1:]:
            accumulated, _ = merge_states(accumulated, artifacts[idx])

        trial_lines = lines(accumulated)
        if canonical is None:
            canonical = trial_lines
        elif trial_lines != canonical:
            saw_violation = True
            break

    assert not saw_violation, \
        "Eventual consistency violated: merging artifacts in different orders diverged."

    # === Bonus: commutativity still holds after all this mayhem ===
    s1, _ = merge_states(ouroboros, carol_rebased)
    s2, _ = merge_states(carol_rebased, ouroboros)
    assert s1 == s2, "Commutativity broken after ouroboros"

    # === Bonus 2: rebasing the ouroboros onto itself is idempotent ===
    r_idem, _ = rebase([ouroboros], ouroboros)
    assert lines(r_idem) == lines(ouroboros), "Idempotent rebase broken on ouroboros"


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
