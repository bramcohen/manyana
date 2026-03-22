# Code for eventually consistent merging and UX for it
# external API is initial_state, current_lines, update_state, and merge_states

# Adding blame to this would be straightforward by attaching a list of
#   commit ids which caused each increment to the count
# Cherry-picking could be supported with UX selecting ranges of lines (probably including invisible dangling deletes
#   which happened just outside them). That results in a state only representing some lines. Lines which are
#   dependent but not part of the cherry can be given count 0.

# state is enough information about the history of a file for future merges
# state size is linear on the history

from .state import serialize_state, deserialize_state
from .diff import get_deletions_and_insertions
from .conflicts import PEACE, conflict_code, show_conflicts
from .tree import state_to_tree, merge_trees

# returns state string
def initial_state(lines):
    return serialize_state([(line, i, False, 1) for i, line in enumerate(lines)])

# reconstructs [line]
def current_lines(raw_state):
    state = deserialize_state(raw_state)
    return [line for (line, depth, anchored_right, count) in state if count % 2]

# Called at commit time
# returns state_string
def update_state(raw_state, lines):
    state = deserialize_state(raw_state)
    if not state:
        return initial_state(lines)
    # Ideally matching would bias towards living lines
    deletions, insertions = get_deletions_and_insertions([x[0] for x in state], lines)
    for deletion in deletions:
        if state[deletion][3] % 2:
            state[deletion][3] += 1
    deleted_set = set(deletions)
    for i in range(len(state)):
        if i not in deleted_set and state[i][3] % 2 == 0:
            state[i][3] += 1
    result = []
    pos_in_insertions = 0
    for pos in range(len(state)+1):
        if pos_in_insertions < len(insertions) and insertions[pos_in_insertions][0] == pos:
            if pos == len(state):
                up = True
            elif pos == 0:
                up = False
            else:
                up = state[pos-1][1] > state[pos][1]
            newlines = insertions[pos_in_insertions][1]
            if up:
                result.append((newlines[0], state[pos-1][1]+1, False, 1))
            else:
                result.append((newlines[0], state[pos][1]+1, True, 1))
            for line in newlines[1:]:
                result.append((line, result[-1][1]+1, False, 1))
            pos_in_insertions += 1
        if pos < len(state):
            result.append(state[pos])
    return serialize_state(result)

# Called when doing a merge
# returns (state_string, file_with_conflict_annotations)
# calling current_lines(state_string) will always give the same values as in the
#   file_with_conflict_annotations but without the conflict annotations
def merge_states(state1, state2):
    tree1 = state_to_tree(deserialize_state(state1))
    tree2 = state_to_tree(deserialize_state(state2))
    status_lines = []
    merge_trees(status_lines, tree1, tree2, False)
    result_lines = []
    begin = 0
    for i in range(len(status_lines)+1):
        if i == len(status_lines) or (status_lines[i][4] and
                status_lines[i][5] and status_lines[i][0].strip()):
            found_add = False
            hit_left = False
            hit_right = False
            for j in range(begin, i):
                line, depth, anchored_right, in_child, on_left, on_right = status_lines[j]
                if on_left != on_right:
                    if (in_child % 2) == on_left:
                        hit_left = True
                    else:
                        hit_right = True
                if (in_child % 2) and on_left != on_right:
                    found_add = True
            if hit_left and hit_right and found_add:
                for j in range(begin, i):
                    line, depth, anchored_right, in_child, on_left, on_right = status_lines[j]
                    if on_left or on_right:
                        result_lines.append((line, conflict_code(in_child % 2, on_left, on_right)))
            else:
                for j in range(begin, i):
                    line, depth, anchored_right, in_child, on_left, on_right = status_lines[j]
                    if in_child % 2:
                        result_lines.append((line, PEACE))
            if i < len(status_lines):
                result_lines.append((status_lines[i][0], PEACE))
            begin = i + 1
    return (serialize_state([x[:4] for x in status_lines]), show_conflicts(result_lines))
