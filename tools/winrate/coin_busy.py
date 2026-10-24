"""the bundle: how many trades the one-position-a-coin rule blocks (any module open on the coin at the entry), their R, by module pair"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
nm = ("⚡", "P/R", "SMC", "EMA")
blk = {}; sd = {}
order = np.argsort(T0, kind="stable")
for i in range(len(T0)):
    on_ = (T0[:i] <= T0[i]) & (T1[:i] > T0[i]) & (CID[:i] == CID[i]) & (MD[:i] != MD[i])
    if on_.any():
        j = np.flatnonzero(on_)[0]; key = (nm[MD[j]], nm[MD[i]]); blk.setdefault(key, []).append(R[i])
for md in range(4):
    ix = MD == md; print(nm[md], "всего", ix.sum(), "средний R", R[ix].mean().round(3))
for k, v in sorted(blk.items(), key=lambda kv: -len(kv[1])):
    print(f"занято {k[0]:4s} → пропущена {k[1]:4s}: {len(v):4d} сделок, средний R {np.mean(v):+.3f}, WR {np.mean(np.array(v) > 0)*100:.0f}%")
