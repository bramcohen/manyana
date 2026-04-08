# Code for eventually consistent merging and UX for it
# external API is initial_state, current_lines, update_state, and merge_states

# Adding blame to this would be straightforward by attaching a list of
#   commit ids which caused each increment to the count
# Cherry-picking could be supported with UX selecting ranges of lines (probably including invisible dangling deletes
#   which happened just outside them). That results in a state only representing some lines. Lines which are
#   dependent but not part of the cherry can be given count 0.

# state is enough information about the history of a file for future merges
# state size is linear on the history

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
                        result_lines.append((line, conflict_code(in_child, on_left, on_right)))
            else:
                for j in range(begin, i):
                    line, depth, anchored_right, in_child, on_left, on_right = status_lines[j]
                    if in_child % 2:
                        result_lines.append((line, PEACE))
            if i < len(status_lines):
                result_lines.append((status_lines[i][0], PEACE))
            begin = i + 1
    return (serialize_state([x[:4] for x in status_lines]), show_conflicts(result_lines))

from difflib import SequenceMatcher

# returns ([deleted_line_number], [(insert_position, [inserted_line])])
def get_deletions_and_insertions(lines1, lines2):
    deletions = []
    insertions = []
    for (tag, l1_begin, l1_end, l2_begin, l2_end) in SequenceMatcher(None, lines1, lines2).get_opcodes():
        if tag in ('delete', 'replace'):
            for i in range(l1_begin, l1_end):
                deletions.append(i)
        if tag in ('insert', 'replace'):
            insertions.append((l1_begin, lines2[l2_begin:l2_end]))
    return (deletions, insertions)

# state format is [(line, depth, anchored_right, count)]
def serialize_state(state):
    result = []
    for (line, depth, anchored_right, count) in state:
        arrow = '>' if anchored_right else '<'
        result.append(f'{depth} {arrow} {count} {line}')
    return '\n'.join(result)

def deserialize_state(mystr):
    result = []
    if mystr == '':
        return []
    for line in mystr.split('\n'):
        vals = line.split(' ')
        result.append([' '.join(vals[3:]), int(vals[0]), vals[1] == '>', int(vals[2])])
    return result

CONFLICT_ADDED_LEFT = 0
CONFLICT_ADDED_RIGHT = 1
CONFLICT_ADDED_BOTH = 2
CONFLICT_DELETED_LEFT = 3
CONFLICT_DELETED_RIGHT = 4
PEACE = 5

conflict_strings = ['added left', 'added right', 'added both',
        'deleted left', 'deleted right', 'deleted both']

END = '>>>>>>> end conflict'

def show_conflicts(result_lines):
    final_result = []
    last_state = PEACE
    for line, new_state in result_lines:
        if new_state == PEACE:
            if last_state != PEACE:
                final_result.append(END)
        elif last_state == PEACE:
            final_result.append('<<<<<<< begin ' + conflict_strings[new_state])
        elif last_state != new_state:
            final_result.append('======= begin ' + conflict_strings[new_state])
        final_result.append(line)
        last_state = new_state
    if last_state != PEACE:
        final_result.append(END)
    return final_result

def conflict_code(in_child, on_left, on_right):
    assert on_left or on_right
    if in_child % 2:
        if on_left and on_right:
            return CONFLICT_ADDED_BOTH
        elif on_left:
            return CONFLICT_ADDED_LEFT
        else:
            return CONFLICT_ADDED_RIGHT
    else:
        if on_right:
            return CONFLICT_DELETED_LEFT
        else:
            return CONFLICT_DELETED_RIGHT

def state_to_tree(state):
    root_children_above = []
    children_above = [[] for i in range(len(state))]
    last_by_depth = [None] * len(state)
    for i in range(len(state)):
        line, depth, anchored_right, count = state[i]
        if not anchored_right:
            if depth == 0:
                root_children_above.append(i)
            else:
                children_above[last_by_depth[depth-1]].append(i)
        last_by_depth[depth] = i
    children_below = [[] for i in range(len(state))]
    last_by_depth = [None] * len(state)
    for i in range(len(state)-1,-1,-1):
        line, depth, anchored_right, count = state[i]
        if anchored_right:
            children_below[last_by_depth[depth-1]].append(i)
        last_by_depth[depth] = i
    for cb in children_below:
        cb.reverse()
    return (None, -1, [], [pull_out_tree(i, state, children_above, children_below) for i in root_children_above], -1)

def pull_out_tree(pos, state, children_above, children_below):
    line, depth, archored_right, count = state[pos]
    return (line, count, [pull_out_tree(x, state, children_above, children_below) for x in children_below[pos]],
        [pull_out_tree(x, state, children_above, children_below) for x in children_above[pos]], depth)

# format of tree is (line, count, [low_trees], [high_trees], depth)
# line is None for the root
# lines in output are of format (line, depth, anchored_right, count, on_left, on_right)
# state format is [(line, depth, anchored_right, count)]
def merge_trees(output, tree1, tree2, anchored_right):
    line1, count1, lowtrees1, hightrees1, depth1 = tree1
    line2, count2, lowtrees2, hightrees2, depth2 = tree2
    assert line1 == line2
    assert depth1 == depth2
    merge_tree_lists(output, lowtrees1, lowtrees2, True)
    if line1 is not None:
        output.append((line1, depth1, anchored_right, max(count1, count2), count1 % 2, count2 % 2))
    merge_tree_lists(output, hightrees1, hightrees2, False)

def merge_tree_lists(output, left_trees, right_trees, anchored_right):
    pos1 = 0
    pos2 = 0
    while pos1 < len(left_trees) or pos2 < len(right_trees):
        if pos2 == len(right_trees):
            insert_tree(output, left_trees[pos1], False, anchored_right)
            pos1 += 1
        elif pos1 == len(left_trees):
            insert_tree(output, right_trees[pos2], True, anchored_right)
            pos2 += 1
        elif left_trees[pos1][0] == right_trees[pos2][0]:
            merge_trees(output, left_trees[pos1], right_trees[pos2], anchored_right)
            pos1 += 1
            pos2 += 1
        elif left_trees[pos1][0] < right_trees[pos2][0]:
            insert_tree(output, left_trees[pos1], False, anchored_right)
            pos1 += 1
        else:
            insert_tree(output, right_trees[pos2], True, anchored_right)
            pos2 += 1

def insert_tree(output, tree, from_right, anchored_right):
    line, count, lowtrees, hightrees, depth = tree
    for new_tree in lowtrees:
        insert_tree(output, new_tree, from_right, True)
    output.append((line, depth, anchored_right, count, not from_right, from_right))
    for new_tree in hightrees:
        insert_tree(output, new_tree, from_right, False)

def test_initial():
    assert initial_state([]) == ''
    assert current_lines('') == []
    v1 = initial_state(['line 1', 'line 4'])
    v2 = initial_state(['line 2', 'line 3'])
    state1, output1 = merge_states(v1, v2)
    state2, output2 = merge_states(v2, v1)
    assert state1 == state2
    assert current_lines(state1) == ['line 1', 'line 4', 'line 2', 'line 3']

def swap_left_right(s):
    s = s.replace('left', 'swap')
    s = s.replace('right', 'left')
    s = s.replace('swap', 'right')
    return s

def check_merges(thing1, thing2, expected_result, expected_conflicts = None):
    state1, conflicts1 = merge_states(thing1, thing2)
    state2, conflicts2 = merge_states(thing2, thing1)
    assert state1 == state2
    if expected_conflicts is None:
        assert conflicts1 == conflicts2 == expected_result
    else:
        assert conflicts1 == expected_conflicts
        assert conflicts2 == [swap_left_right(x) for x in expected_conflicts]
    assert current_lines(state1) == expected_result

SAL = '<<<<<<< begin added left'
SAR = '<<<<<<< begin added right'
SAB = '<<<<<<< begin added both'
SDL = '<<<<<<< begin deleted left'
SDR = '<<<<<<< begin deleted right'
SDB = '<<<<<<< begin deleted both'
MAL = '======= begin added left'
MAR = '======= begin added right'
MAB = '======= begin added both'
MDL = '======= begin deleted left'
MDR = '======= begin deleted right'
MDB = '======= begin deleted both'

def test_bottom_and_top():
    initial = initial_state(['A'])
    insert_below = update_state(initial, ['B', 'A'])
    replace_below = update_state(insert_below, ['B'])
    insert_above = update_state(initial, ['A', 'B'])
    replace_above = update_state(insert_above, ['B'])
    delete = update_state(initial, [])
    check_merges(initial, initial, ['A'])
    check_merges(initial, insert_below, ['B', 'A'])
    check_merges(initial, replace_below, ['B'])
    check_merges(initial, insert_above, ['A', 'B'])
    check_merges(initial, replace_above, ['B'])
    check_merges(initial, delete, [])
    check_merges(insert_below, insert_below, ['B', 'A'])
    check_merges(insert_below, replace_below, ['B'])
    check_merges(insert_below, insert_above, ['B', 'A', 'B'])
    check_merges(insert_below, replace_above, ['B', 'B'], [SAL, 'B', MDR, 'A', MAR, 'B', END])
    check_merges(insert_below, delete, ['B'], [SAL, 'B', MDR, 'A', END])
    check_merges(replace_below, replace_below, ['B'])
    check_merges(replace_below, insert_above, ['B', 'B'], [SAL, 'B', MDL, 'A', MAR, 'B', END])
    check_merges(replace_below, replace_above, ['B', 'B'], [SAL, 'B', MAR, 'B', END])
    check_merges(replace_below, delete, ['B'])
    check_merges(insert_above, insert_above, ['A', 'B'])
    check_merges(insert_above, replace_above, ['B'])
    check_merges(insert_above, delete, ['B'], [SDR, 'A', MAL, 'B', END])
    check_merges(replace_above, replace_above, ['B'])
    check_merges(replace_above, delete, ['B'])
    check_merges(delete, delete, [])

def test_bottom():
    initial = initial_state(['A', 'X'])
    insert_below = update_state(initial, ['B', 'A', 'X'])
    replace_below = update_state(insert_below, ['B', 'X'])
    insert_above = update_state(initial, ['A', 'B', 'X'])
    replace_above = update_state(insert_above, ['B', 'X'])
    delete = update_state(initial, ['X'])
    check_merges(initial, initial, ['A', 'X'])
    check_merges(initial, insert_below, ['B', 'A', 'X'])
    check_merges(initial, replace_below, ['B', 'X'])
    check_merges(initial, insert_above, ['A', 'B', 'X'])
    check_merges(initial, replace_above, ['B', 'X'])
    check_merges(initial, delete, ['X'])
    check_merges(insert_below, insert_below, ['B', 'A', 'X'])
    check_merges(insert_below, replace_below, ['B', 'X'])
    check_merges(insert_below, insert_above, ['B', 'A', 'B', 'X'])
    check_merges(insert_below, replace_above, ['B', 'B', 'X'], [SAL, 'B', MDR, 'A', MAR, 'B', END, 'X'])
    check_merges(insert_below, delete, ['B', 'X'], [SAL, 'B', MDR, 'A', END, 'X'])
    check_merges(replace_below, replace_below, ['B', 'X'])
    check_merges(replace_below, insert_above, ['B', 'B', 'X'], [SAL, 'B', MDL, 'A', MAR, 'B', END, 'X'])
    check_merges(replace_below, replace_above, ['B', 'B', 'X'], [SAL, 'B', MAR, 'B', END, 'X'])
    check_merges(replace_below, delete, ['B', 'X'])
    check_merges(insert_above, insert_above, ['A', 'B', 'X'])
    check_merges(insert_above, replace_above, ['B', 'X'])
    check_merges(insert_above, delete, ['B', 'X'], [SDR, 'A', MAL, 'B', END, 'X'])
    check_merges(replace_above, replace_above, ['B', 'X'])
    check_merges(replace_above, delete, ['B', 'X'])
    check_merges(delete, delete, ['X'])

def test_top():
    initial = initial_state(['X', 'A'])
    insert_below = update_state(initial, ['X', 'B', 'A'])
    replace_below = update_state(insert_below, ['X', 'B'])
    insert_above = update_state(initial, ['X', 'A', 'B'])
    replace_above = update_state(insert_above, ['X', 'B'])
    delete = update_state(initial, ['X'])
    check_merges(initial, initial, ['X', 'A'])
    check_merges(initial, insert_below, ['X', 'B', 'A'])
    check_merges(initial, replace_below, ['X', 'B'])
    check_merges(initial, insert_above, ['X', 'A', 'B'])
    check_merges(initial, replace_above, ['X', 'B'])
    check_merges(initial, delete, ['X'])
    check_merges(insert_below, insert_below, ['X', 'B', 'A'])
    check_merges(insert_below, replace_below, ['X', 'B'])
    check_merges(insert_below, insert_above, ['X', 'B', 'A', 'B'])
    check_merges(insert_below, replace_above, ['X', 'B', 'B'], ['X', SAL, 'B', MDR, 'A', MAR, 'B', END])
    check_merges(insert_below, delete, ['X', 'B'], ['X', SAL, 'B', MDR, 'A', END])
    check_merges(replace_below, replace_below, ['X', 'B'])
    check_merges(replace_below, insert_above, ['X', 'B', 'B'], ['X', SAL, 'B', MDL, 'A', MAR, 'B', END])
    check_merges(replace_below, replace_above, ['X', 'B', 'B'], ['X', SAL, 'B', MAR, 'B', END])
    check_merges(replace_below, delete, ['X', 'B'])
    check_merges(insert_above, insert_above, ['X', 'A', 'B'])
    check_merges(insert_above, replace_above, ['X', 'B'])
    check_merges(insert_above, delete, ['X', 'B'], ['X', SDR, 'A', MAL, 'B', END])
    check_merges(replace_above, replace_above, ['X', 'B'])
    check_merges(replace_above, delete, ['X', 'B'])
    check_merges(delete, delete, ['X'])

def test_generation_counting():
    count0 = initial_state([])
    count1 = update_state(count0, ['A'])
    count2 = update_state(count1, [])
    count3 = update_state(count2, ['A'])
    count4 = update_state(count3, [])
    check_merges(count0, count1, ['A'])
    check_merges(count0, count2, [])
    check_merges(count0, count3, ['A'])
    check_merges(count0, count4, [])
    check_merges(count1, count1, ['A'])
    check_merges(count1, count2, [])
    check_merges(count1, count3, ['A'])

    check_merges(count1, count4, [])
    check_merges(count2, count2, [])
    check_merges(count2, count3, ['A'])
    check_merges(count2, count4, [])
    check_merges(count3, count3, ['A'])
    check_merges(count3, count4, [])
    check_merges(count4, count4, [])

def test_insertions_single(a, b, c, d):
    state1, junk1 = merge_states(a, b)
    state2, junk2 = merge_states(c, d)
    state3, junk3 = merge_states(state1, state2)
    assert current_lines(state3) == ['A', 'B', 'C', 'D']

from itertools import permutations

def test_insertions():
    mylist = [initial_state([x]) for x in ('A', 'B', 'C', 'D')]
    for perm in permutations(mylist):
        test_insertions_single(*mylist)

def test_insertions_below_single(a, b, c, d):
    state1, junk1 = merge_states(a, b)
    state2, junk2 = merge_states(c, d)
    state3, junk3 = merge_states(state1, state2)
    assert current_lines(state3) == ['A', 'B', 'C', 'D', 'X']

def test_insertions_below():
    initial = initial_state(['X'])
    mylist = [update_state(initial, [x, 'X']) for x in ('A', 'B', 'C', 'D')]
    for perm in permutations(mylist):
        test_insertions_below_single(*mylist)

def test_space_separated_insert_insert():
    initial = initial_state([''])
    insert_left = update_state(initial, ['A', ''])
    insert_right = update_state(initial, ['', 'B'])
    check_merges(insert_left, insert_right, ['A', '', 'B'], [SAL, 'A', MAB, '', MAR, 'B', END])

def test_space_separated_insert_delete():
    initial = initial_state(['', 'B'])
    insert_left = update_state(initial, ['A', '', 'B'])
    delete_right = update_state(initial, [''])
    check_merges(insert_left, delete_right, ['A', ''], [SAL, 'A', MAB, '', MDR, 'B', END])

def test_space_separated_delete_insert():
    initial = initial_state(['A', ''])
    delete_left = update_state(initial, [''])
    insert_right = update_state(initial, ['A', '', 'B'])
    check_merges(delete_left, insert_right, ['', 'B'], [SDL, 'A', MAB, '', MAR, 'B', END])

def test_space_separated_delete_delete():
    initial = initial_state(['A', '', 'B'])
    delete_left = update_state(initial, ['', 'B'])
    delete_right = update_state(initial, ['A', ''])
    check_merges(delete_left, delete_right, [''])

def test_deleted_both():
    initial = initial_state(['', 'X', ''])
    left = update_state(initial, ['A', '', ''])
    right = update_state(initial, ['', '', 'B'])
    check_merges(left, right, ['A', '', '', 'B'], [SAL, 'A', MAB, '', '', MAR, 'B', END])

def test_deleted_both2():
    initial = initial_state(['A'])
    left = update_state(initial, ['X', 'A'])
    left = update_state(left, ['X'])
    right = update_state(initial, ['A', 'Y'])
    right = update_state(initial, ['Y'])
    check_merges(left, right, ['X', 'Y'], [SAL, 'X', MAR, 'Y', END])

def test_update_insert_multiple():
    initial = initial_state(['A', 'B'])
    updated = update_state(initial, ['A', 'X', 'Y', 'B'])
    assert current_lines(updated) == ['A', 'X', 'Y', 'B']

def test_insert_low_tree():
    initial = initial_state(['A'])
    updated = update_state(initial, ['Y', 'A'])
    updated = update_state(updated, ['X', 'Y', 'A'])
    right = update_state(initial, ['A', 'B'])
    check_merges(updated, right, ['X', 'Y', 'A', 'B'])

if __name__ == '__main__':
    import inspect
    for name, func in list(globals().items()):
        if name.startswith('test') and callable(func) and not inspect.signature(func).parameters:
            func()
