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
