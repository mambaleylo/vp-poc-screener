import sys, os, io, contextlib
sys.argv = ["x"]
sys.path.insert(0, "/home/user/vp-poc-screener")
with contextlib.redirect_stdout(io.StringIO()):
    import vp_poc_screener as V
D = os.path.dirname(os.path.abspath(__file__))

def load(sym, tf="1h"):
    fn = f"{D}/data/{tf}/{sym}.csv"
    if not os.path.exists(fn):
        return None
    out = []
    last = None
    with open(fn) as f:
        for line in f:
            t, o, h, l, c, v = line.split(",")
            t = int(t)
            if last is not None and t <= last:
                continue
            last = t
            out.append({"time": t, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
    return out

def coins(tf="1h"):
    return sorted(f[:-4] for f in os.listdir(f"{D}/data/{tf}") if f.endswith(".csv"))
