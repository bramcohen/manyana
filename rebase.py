# History-preserving rebase for manyana's CRDT.
#
# Both modes share a core: at each step, dag.merge(running_base, local_i)
# with primary=running_base, recorded as kind=REBASE_STEP.  The primary
# chain from the tip is the rebased trunk; the original local commits
# remain reachable via non-primary parents.
#
# The "primary ancestor" annotation is advisory — it tells a DAG viewer
# which parent is the "trunk" line.  It doesn't affect merge semantics.

from manyana import REBASE_STEP, BEGIN_PREFIX, DIVIDER_PREFIX, END


def _is_conflict_marker(line):
    return (line.startswith(BEGIN_PREFIX) or
            line.startswith(DIVIDER_PREFIX) or
            line == END)


def rebase_jam(dag, local_chain, new_base):
    """Replay local_chain on top of new_base in one shot.
    Returns (final_id, [step_id, ...], [annotated_per_step, ...]).
    The third list is parallel to steps: each entry is the annotated
    output of that step's merge.  kind=REBASE_STEP on the DAG record
    already encodes 'this is a rebase step', so the original commit
    message is preserved verbatim."""
    running = new_base
    steps = []
    annotations = []
    for local in local_chain:
        cid, annotated = dag.merge(
            running, local, primary=running, kind=REBASE_STEP,
            message=dag.commits[local]['message'],
        )
        steps.append(cid)
        annotations.append(annotated)
        running = cid
    return running, steps, annotations


def rebase_interactive(dag, local_chain, new_base, *, pause='conflict'):
    """Generator. Yields (step_id, annotated) at each pause point.

    pause in {'conflict','always'}:
      'conflict' — yield only when the merge surfaces conflict markers
      'always'   — yield once per local commit, conflicts or not

    At each yield the caller may either:
      g.send(fixup_id) — splice in a resolution.  The fixup's state
                         becomes the new running base for the next step;
                         the conflicted step still exists in the DAG and
                         is reachable as fixup's primary parent.
      next(g)          — accept the yielded step as-is (equivalent to
                         send(None)).  The conflicted step's *state*
                         becomes the running base for the next step;
                         that state is a well-formed CRDT state in
                         which both contested versions of disputed
                         regions coexist.  The conflict markers only
                         appear in the yielded annotated output and
                         do not feed back into anything.  Useful for
                         batch tooling that wants to surface the
                         rebase first and resolve later.
    """
    if pause not in ('conflict', 'always'):
        raise ValueError(f"pause must be 'conflict' or 'always', got {pause!r}")
    running = new_base
    for local in local_chain:
        cid, annotated = dag.merge(
            running, local, primary=running, kind=REBASE_STEP,
            message=dag.commits[local]['message'],
        )
        has_conflict = any(_is_conflict_marker(line) for line in annotated)
        if pause == 'always' or has_conflict:
            fixup = yield (cid, annotated)
            if fixup is not None:
                running = fixup
                continue
        running = cid
