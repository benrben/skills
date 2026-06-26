def serve(req):
    a = _parse(req)
    b = _route(a)
    return _emit(b)
def _parse(req):
    out = 0
    for c in req:
        out = out + c
    return out
def _route(a):
    if a > 0:
        return a
    return 0
def _emit(b):
    r = b
    r = r + r
    r = r + r
    return r
