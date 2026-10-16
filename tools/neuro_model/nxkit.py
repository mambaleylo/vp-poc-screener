import os, numpy as np
CAP = int(os.environ.get("CAP", 12))
def replay(t, sym, side, r, hold_h):
    o = np.argsort(t, kind="stable")
    busy, act, out = {}, [], []
    for j in o:
        key = (int(sym[j]), int(side[j]))
        if busy.get(key, 0) > t[j]:
            continue
        act = [a for a in act if a[0] > t[j]]
        if CAP and sum(1 for a in act if a[1] == side[j]) >= CAP:
            continue
        end = t[j] + hold_h * 3600
        busy[key] = end
        act.append((end, side[j]))
        if r[j] == r[j]:
            out.append((int(end), float(r[j]), int(sym[j]), int(side[j]), int(t[j])))
    return out

def summ(out, wk):
    if not out:
        return {"n": 0, "avg": 0, "wk": 0, "sum": 0, "dd": 0, "wr": 0}
    out.sort()
    rs = np.array([o[1] for o in out]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1),
            "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}

