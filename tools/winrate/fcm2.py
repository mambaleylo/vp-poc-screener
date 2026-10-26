exec(open("fcm.py").read().split('for fn in ("fc_f_180_0.995.json"')[0])
def last12(A, rk):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64); r_ = np.where(md != 0, r_ - 0.03, r_)
    return sim6(t0, t1, r_, st_, sth, buf, md, ci, np.ones(6, np.bool_), np.array(rk) / 100, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)[0]
X = lst("fc_f_180_0.995.json")
print("12 мес: сейчас", round(last12(B2, [4.5, 3, 2.5, 2, 2.0, 0])), "| +классика наоборот 1%", round(last12(np.vstack([B2, X]), [4.5, 3, 2.5, 2, 2.0, 1.0])), "| 2%", round(last12(np.vstack([B2, X]), [4.5, 3, 2.5, 2, 2.0, 2.0])))
y, d = go(np.vstack([B2, X]), [4.5, 3, 2.5, 2, 2.0, 2.0]); q = y / ref2; o = np.argsort(q)[:5]
print("худшие окна (старт: сейчас → с классикой):", [(str(np.datetime64(int(roll2[i]), 's'))[:10], int(ref2[i]), int(y[i])) for i in o])
