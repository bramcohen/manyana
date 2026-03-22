# state format is [(line, depth, anchored_right, count)]
def serialize_state(state):
    result = []
    for (line, depth, anchored_right, count) in state:
        result.append(f'{depth} {['<', '>'][anchored_right]} {count} {line}')
    return '\n'.join(result)

def deserialize_state(mystr):
    result = []
    if mystr == '':
        return []
    for line in mystr.split('\n'):
        vals = line.split(' ')
        result.append([' '.join(vals[3:]), int(vals[0]), vals[1] == '>', int(vals[2])])
    return result
