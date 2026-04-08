# History-preserving rebase for manyana's CRDT
#
# Rebase replays a sequence of local commits on top of a new base via
# sequential merges.  Because merge_states is commutative and the weave
# encodes full history, this produces correct results without destroying
# any history.
#
# The "primary ancestor" metadata described in the README is advisory —
# it tells a DAG viewer which parent is the "trunk" line.  It doesn't
# affect the merge algorithm at all.

from manyana import merge_states, update_state, current_lines, initial_state


def rebase(local_states, new_base):
    """Replay a sequence of local commit states on top of new_base.

    Args:
        local_states: list of state strings, one per local commit, in order.
                      Each is the full CRDT state after that commit.
        new_base:     the state string of the new base to rebase onto.

    Returns:
        (final_state, steps)

        final_state: the CRDT state after all local commits have been replayed.
        steps: list of dicts, one per local commit:
            {
                'state':      merged state string after this step,
                'conflicts':  annotated conflict lines ([] if clean),
                'primary':    the primary ancestor state (the running base),
            }
    """
    if not local_states:
        return (new_base, [])

    current = new_base
    steps = []
    for local in local_states:
        merged_state, annotated = merge_states(current, local)
        has_conflicts = any(_is_conflict_marker(line) for line in annotated)
        steps.append({
            'state': merged_state,
            'conflicts': annotated if has_conflicts else [],
            'primary': current,
        })
        current = merged_state

    return (current, steps)


def rebase_from_edits(base_state, local_edits, new_base):
    """Convenience wrapper: rebase a sequence of edits (as line lists).

    Args:
        base_state:  the state string of the original fork point.
        local_edits: list of [line, ...] lists, one per local commit.
        new_base:    the state string to rebase onto.

    Returns:
        Same as rebase(): (final_state, steps)
    """
    state = base_state
    local_states = []
    for lines in local_edits:
        state = update_state(state, lines)
        local_states.append(state)
    return rebase(local_states, new_base)


def _is_conflict_marker(line):
    return (line.startswith('<<<<<<< begin ') or
            line.startswith('======= begin ') or
            line == '>>>>>>> end conflict')
