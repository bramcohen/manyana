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
    if in_child:
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
