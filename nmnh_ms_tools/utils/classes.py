"""Defines methods used across internal classes"""




def str_class(inst, attributes=None):
    """Convenience function to depict a class as a string"""
    if attributes is None:
        attributes = inst.attributes
    rows = [('class', inst.__class__.__name__)]
    for attr in attributes:
        val = getattr(inst, attr)
        if val or val == 0:
            if not isinstance(val, list):
                val = [val]
            for val in val:
                rows.append((attr, val))
                attr = ''
    maxlen = max([len(row[0]) for row in rows])
    return '\n'.join(['{}: {}'.format(a.ljust(maxlen), v) for a, v in rows])


def repr_class(inst, attributes=None):
    """Convenience function to represent major attributes of a class"""
    if attributes is None:
        attributes = inst.attributes
    attrs = ['{}={}'.format(a, getattr(inst, a)) for a in attributes]
    return '{}({})'.format(inst.__class__.__name__, ', '.join(attrs))
