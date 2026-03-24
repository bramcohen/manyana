from typing import Optional
from itertools import permutations
from manyana import initial_state, merge_states, current_lines, update_state, END
import unittest


def swap_left_right(s: str) -> str:
    s = s.replace('left', 'swap')
    s = s.replace('right', 'left')
    s = s.replace('swap', 'right')
    return s

def check_merges(thing1: str, thing2: str, expected_result: list[str], expected_conflicts: Optional[list[str]] = None):
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

def test_insertions_below_single(a: str, b: str, c: str, d: str):
    state1, _ = merge_states(a, b)
    state2, _ = merge_states(c, d)
    state3, _ = merge_states(state1, state2)
    assert current_lines(state3) == ['A', 'B', 'C', 'D', 'X']

def test_insertions_single(a: str, b: str, c: str, d: str):
    state1, _ = merge_states(a, b)
    state2, _ = merge_states(c, d)
    state3, _ = merge_states(state1, state2)
    assert current_lines(state3) == ['A', 'B', 'C', 'D']

class Tests(unittest.TestCase):
    def test_initial(self):
        assert initial_state([]) == ''
        assert current_lines('') == []
        v1 = initial_state(['line 1', 'line 4'])
        v2 = initial_state(['line 2', 'line 3'])
        state1, _ = merge_states(v1, v2)
        state2, _ = merge_states(v2, v1)
        assert state1 == state2
        assert current_lines(state1) == ['line 1', 'line 4', 'line 2', 'line 3']

    def test_bottom_and_top(self):
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

    def test_bottom(self):
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

    def test_top(self):
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

    def test_generation_counting(self):
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

    def test_insertions(self):
        mylist = [initial_state([x]) for x in ('A', 'B', 'C', 'D')]
        for _ in permutations(mylist):
            test_insertions_single(*mylist)

    def test_insertions_below(self):
        initial = initial_state(['X'])
        mylist = [update_state(initial, [x, 'X']) for x in ('A', 'B', 'C', 'D')]
        for _ in permutations(mylist):
            test_insertions_below_single(*mylist)

    def test_space_separated_insert_insert(self):
        initial = initial_state([''])
        insert_left = update_state(initial, ['A', ''])
        insert_right = update_state(initial, ['', 'B'])
        check_merges(insert_left, insert_right, ['A', '', 'B'], [SAL, 'A', MAB, '', MAR, 'B', END])

    def test_space_separated_insert_delete(self):
        initial = initial_state(['', 'B'])
        insert_left = update_state(initial, ['A', '', 'B'])
        delete_right = update_state(initial, [''])
        check_merges(insert_left, delete_right, ['A', ''], [SAL, 'A', MAB, '', MDR, 'B', END])

    def test_space_separated_delete_insert(self):
        initial = initial_state(['A', ''])
        delete_left = update_state(initial, [''])
        insert_right = update_state(initial, ['A', '', 'B'])
        check_merges(delete_left, insert_right, ['', 'B'], [SDL, 'A', MAB, '', MAR, 'B', END])

    def test_space_separated_delete_delete(self):
        initial = initial_state(['A', '', 'B'])
        delete_left = update_state(initial, ['', 'B'])
        delete_right = update_state(initial, ['A', ''])
        check_merges(delete_left, delete_right, [''])

    def test_deleted_both(self):
        initial = initial_state(['', 'X', ''])
        left = update_state(initial, ['A', '', ''])
        right = update_state(initial, ['', '', 'B'])
        check_merges(left, right, ['A', '', '', 'B'], [SAL, 'A', MAB, '', '', MAR, 'B', END])

    def test_deleted_both2(self):
        initial = initial_state(['A'])
        left = update_state(initial, ['X', 'A'])
        left = update_state(left, ['X'])
        right = update_state(initial, ['A', 'Y'])
        right = update_state(initial, ['Y'])
        check_merges(left, right, ['X', 'Y'], [SAL, 'X', MAR, 'Y', END])

    def test_update_insert_multiple(self):
        initial = initial_state(['A', 'B'])
        updated = update_state(initial, ['A', 'X', 'Y', 'B'])
        assert current_lines(updated) == ['A', 'X', 'Y', 'B']

    def test_insert_low_tree(self):
        initial = initial_state(['A'])
        updated = update_state(initial, ['Y', 'A'])
        updated = update_state(updated, ['X', 'Y', 'A'])
        right = update_state(initial, ['A', 'B'])
        check_merges(updated, right, ['X', 'Y', 'A', 'B'])


if __name__ == '__main__':
    unittest.main()
