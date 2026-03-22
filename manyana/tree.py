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
