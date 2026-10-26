"""the header's yearly expectation (port_risk4.py's way: no friction, rolling 12-month windows from $100) for the bundle
as deployed and the bundle + 📏 HTF (the deployed list htf_bt_v1.json, 1.5%)"""
import numpy as np, warnings, json; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("recent = ")[0])
def hdr(A, rk):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    use = np.ones(5, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = f(ts(2025, 10), ts(2026, 10))
    return {"p10": int(np.percentile(y, 10)), "p50": int(np.median(y)), "p90": int(np.percentile(y, 90)), "dd": int(round(np.median(dd) * 100)), "last12": int(l[0])}, l[2].astype(int).tolist()
print("bundle", *hdr(BASE, [4.5, 3, 2.5, 2, 0]), flush=True)
print("bundle_htf 1.5", *hdr(np.vstack([BASE, rows("htf_bt_v1.json")]), [4.5, 3, 2.5, 2, 1.5]), flush=True)
print("bundle_htf 2.0", *hdr(np.vstack([BASE, rows("htf_bt_v1.json")]), [4.5, 3, 2.5, 2, 2.0]), flush=True)
