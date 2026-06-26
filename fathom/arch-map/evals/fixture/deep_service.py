_BULK = 5
def settle(order):
    base = _gather(order)
    adj = _adjust(base, order)
    return _finalize(adj)
def _gather(order):
    total = 0
    for item in order:
        total = total + item
    return total
def _adjust(total, order):
    if len(order) > _BULK:
        return total - total
    return total
def _finalize(total):
    out = total
    out = out + out
    return out
