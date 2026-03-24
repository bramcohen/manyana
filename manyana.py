from typing import Optional, TypeAlias, TypeVar
from difflib import SequenceMatcher
from enum import unique, Enum
from dataclasses import dataclass

# Code for eventually consistent merging and UX for it
# external API is initial_state, current_lines, update_state, and merge_states

# Adding blame to this would be straightforward by attaching a list of
#   commit ids which caused each increment to the count
# Cherry-picking could be supported with UX selecting ranges of lines (probably including invisible dangling deletes
#   which happened just outside them). That results in a state only representing some lines. Lines which are
#   dependent but not part of the cherry can be given count 0.

# state is enough information about the history of a file for future merges
# state size is linear on the history

@dataclass(frozen=True)
class StateItem:
    line: str
    depth: int
    anchored_right: bool
    count: int

State: TypeAlias = list[StateItem]

@dataclass(frozen=True)
class OutputItem:
    line: Optional[str]
    depth: int
    anchored_right: bool
    count: int
    on_left: int
    on_right: int

Output: TypeAlias = list[OutputItem]

@dataclass(frozen=True)
class Tree:
    line: Optional[str]
    count: int
    low_trees: list["Tree"]
    high_trees: list["Tree"]
    depth: int

T = TypeVar("T")
def _unwrap(x: Optional[T]) -> T:
    if x is None:
        raise ValueError("_unwrap called on None")
    return x

# returns state string
def initial_state(lines: list[str]) -> str:
    return serialize_state([StateItem(line, i, False, 1) for i, line in enumerate(lines)])

# reconstructs [line]
def current_lines(raw_state: str) -> list[str]:
    state = deserialize_state(raw_state)
    return [x.line for x in state if x.count % 2]

# Called at commit time
# returns state_string
def update_state(raw_state: str, lines: list[str]) -> str:
    state = deserialize_state(raw_state)
    if not state:
        return initial_state(lines)
    # Ideally matching would bias towards living lines
    deletions, insertions = get_deletions_and_insertions([x.line for x in state], lines)
    for deletion in deletions:
        if state[deletion].count % 2 == 1:
            state[deletion] = _incr_count(state[deletion])
    deleted_set = set(deletions)
    for i in range(len(state)):
        if i not in deleted_set and state[i].count % 2 == 0:
            state[i] = _incr_count(state[i])
    result: State = []
    pos_in_insertions = 0
    for pos in range(len(state)+1):
        if pos_in_insertions < len(insertions) and insertions[pos_in_insertions][0] == pos:
            if pos == len(state):
                up = True
            elif pos == 0:
                up = False
            else:
                up = state[pos-1].depth > state[pos].depth
            newlines = insertions[pos_in_insertions][1]
            if up:
                result.append(StateItem(newlines[0], state[pos-1].depth+1, False, 1))
            else:
                result.append(StateItem(newlines[0], state[pos].depth+1, True, 1))
            for line in newlines[1:]:
                result.append(StateItem(line, result[-1].depth+1, False, 1))
            pos_in_insertions += 1
        if pos < len(state):
            result.append(state[pos])
    return serialize_state(result)

def _incr_count(x: StateItem) -> StateItem:
    return StateItem(x.line, x.depth, x.anchored_right, x.count+1)

# Called when doing a merge
# returns (state_string, file_with_conflict_annotations)
# calling current_lines(state_string) will always give the same values as in the
#   file_with_conflict_annotations but without the conflict annotations
def merge_states(state1: str, state2: str) -> tuple[str, list[str]]:
    tree1 = state_to_tree(deserialize_state(state1))
    tree2 = state_to_tree(deserialize_state(state2))
    status_lines: Output = []
    merge_trees(status_lines, tree1, tree2, False)
    result_lines: list[tuple[str, Conflict]] = []
    begin = 0
    for i in range(len(status_lines)+1):
        if i == len(status_lines) or (status_lines[i].on_left and
                status_lines[i].on_right and _unwrap(status_lines[i].line).strip()):
            found_add = False
            hit_left = False
            hit_right = False
            for j in range(begin, i):
                status_line = status_lines[j]
                if status_line.on_left != status_line.on_right:
                    if status_line.count == status_line.on_left:
                        hit_left = True
                    else:
                        hit_right = True
                if status_line.count and status_line.on_left != status_line.on_right:
                    found_add = True
            if hit_left and hit_right and found_add:
                for j in range(begin, i):
                    status_line = status_lines[j]
                    if status_line.on_left or status_line.on_right:
                        result_lines.append((_unwrap(status_line.line), conflict_code(status_line.count, status_line.on_left, status_line.on_right)))
            else:
                for j in range(begin, i):
                    status_line = status_lines[j]
                    if status_line.count:
                        result_lines.append((_unwrap(status_line.line), Conflict.PEACE))
            if i < len(status_lines):
                result_lines.append((_unwrap(status_lines[i].line), Conflict.PEACE))
            begin = i + 1
    return (serialize_state([_output_item_to_state_item(x) for x in status_lines]), show_conflicts(result_lines))

def _output_item_to_state_item(x: OutputItem) -> StateItem:
    return StateItem(_unwrap(x.line), x.depth, x.anchored_right, x.count)

# returns ([deleted_line_number], [(insert_position, [inserted_line])])
def get_deletions_and_insertions(lines1: list[str], lines2: list[str]) -> tuple[list[int], list[tuple[int, list[str]]]]:
    deletions: list[int] = []
    insertions: list[tuple[int, list[str]]] = []
    for (tag, l1_begin, l1_end, l2_begin, l2_end) in SequenceMatcher(None, lines1, lines2).get_opcodes():
        if tag in ('delete', 'replace'):
            for i in range(l1_begin, l1_end):
                deletions.append(i)
        if tag in ('insert', 'replace'):
            insertions.append((l1_begin, lines2[l2_begin:l2_end]))
    return (deletions, insertions)

def serialize_state(state: State) -> str:
    result: list[str] = []
    for x in state:
        result.append(f'{x.depth} {['<', '>'][x.anchored_right]} {x.count} {x.line}')
    return '\n'.join(result)

def deserialize_state(mystr: str) -> State:
    result: State = []
    if mystr == '':
        return []
    for line in mystr.split('\n'):
        vals = line.split(' ')
        result.append(StateItem(' '.join(vals[3:]), int(vals[0]), vals[1] == '>', int(vals[2])))
    return result

CONFLICT_STRS = ['added left', 'added right', 'added both',
        'deleted left', 'deleted right', 'deleted both']

@unique
class Conflict(Enum):
    ADDED_LEFT = 0
    ADDED_RIGHT = 1
    ADDED_BOTH = 2
    DELETED_LEFT = 3
    DELETED_RIGHT = 4
    PEACE = 5

    def to_str(self) -> str:
        return CONFLICT_STRS[self.value]

END = '>>>>>>> end conflict'

def show_conflicts(result_lines: list[tuple[str, Conflict]]) -> list[str]:
    final_result: list[str] = []
    last_state = Conflict.PEACE
    for line, new_state in result_lines:
        if new_state == Conflict.PEACE:
            if last_state != Conflict.PEACE:
                final_result.append(END)
        elif last_state == Conflict.PEACE:
            final_result.append('<<<<<<< begin ' + new_state.to_str())
        elif last_state != new_state:
            final_result.append('======= begin ' + new_state.to_str())
        final_result.append(line)
        last_state = new_state
    if last_state != Conflict.PEACE:
        final_result.append(END)
    return final_result

def conflict_code(in_child: int, on_left: int, on_right: int) -> Conflict:
    assert on_left or on_right
    if in_child:
        if on_left and on_right:
            return Conflict.ADDED_BOTH
        elif on_left:
            return Conflict.ADDED_LEFT
        else:
            return Conflict.ADDED_RIGHT
    else:
        if on_right:
            return Conflict.DELETED_LEFT
        else:
            return Conflict.DELETED_RIGHT

def state_to_tree(state: State) -> Tree:
    root_children_above: list[int] = []
    children_above: list[list[int]] = [[] for _ in range(len(state))]
    last_by_depth: list[Optional[int]] = [None] * len(state)
    for i in range(len(state)):
        state_item = state[i]
        if not state_item.anchored_right:
            if state_item.depth == 0:
                root_children_above.append(i)
            else:
                children_above[_unwrap(last_by_depth[state_item.depth-1])].append(i)
        last_by_depth[state_item.depth] = i
    children_below: list[list[int]] = [[] for _ in range(len(state))]
    last_by_depth = [None] * len(state)
    for i in range(len(state)-1,-1,-1):
        state_item = state[i]
        if state_item.anchored_right:
            children_below[_unwrap(last_by_depth[state_item.depth-1])].append(i)
        last_by_depth[state_item.depth] = i
    for cb in children_below:
        cb.reverse()
    return Tree(None, -1, [], [pull_out_tree(i, state, children_above, children_below) for i in root_children_above], -1)

def pull_out_tree(pos: int, state: State, children_above: list[list[int]], children_below: list[list[int]]) -> Tree:
    state_item = state[pos]
    return Tree(
        state_item.line,
        state_item.count,
        [pull_out_tree(x, state, children_above, children_below) for x in children_below[pos]],
        [pull_out_tree(x, state, children_above, children_below) for x in children_above[pos]],
        state_item.depth
    )

# line is None for the root
def merge_trees(output: Output, tree1: Tree, tree2: Tree, anchored_right: bool):
    assert tree1.line == tree2.line
    assert tree1.depth == tree2.depth
    merge_tree_lists(output, tree1.low_trees, tree2.low_trees, True)
    if tree1.line is not None:
        output.append(OutputItem(
            tree1.line,
            tree1.depth,
            anchored_right,
            max(tree1.count, tree2.count) % 2,
            tree1.count % 2,
            tree2.count % 2,
        ))
    merge_tree_lists(output, tree1.high_trees, tree2.high_trees, False)

def merge_tree_lists(output: Output, left_trees: list[Tree], right_trees: list[Tree], anchored_right: bool):
    pos1 = 0
    pos2 = 0
    while pos1 < len(left_trees) or pos2 < len(right_trees):
        if pos2 == len(right_trees):
            insert_tree(output, left_trees[pos1], False, anchored_right)
            pos1 += 1
        elif pos1 == len(left_trees):
            insert_tree(output, right_trees[pos2], True, anchored_right)
            pos2 += 1
        elif left_trees[pos1].line == right_trees[pos2].line:
            merge_trees(output, left_trees[pos1], right_trees[pos2], anchored_right)
            pos1 += 1
            pos2 += 1
        elif _unwrap(left_trees[pos1].line) < _unwrap(right_trees[pos2].line):
            insert_tree(output, left_trees[pos1], False, anchored_right)
            pos1 += 1
        else:
            insert_tree(output, right_trees[pos2], True, anchored_right)
            pos2 += 1

def insert_tree(output: Output, tree: Tree, from_right: bool, anchored_right: bool):
    for new_tree in tree.low_trees:
        insert_tree(output, new_tree, from_right, True)
    output.append(OutputItem(
        tree.line,
        tree.depth,
        anchored_right,
        tree.count % 2,
        not from_right,
        from_right,
    ))
    for new_tree in tree.high_trees:
        insert_tree(output, new_tree, from_right, False)
