import numpy as np
exec(open("rb_cap.py").read().split("CONF = []")[0])
ATRP = np.array([e[3]["atrp"] for e in ev]); D200 = np.array([e[3]["dist200"] for e in ev])
def run(N, K, sk, xn, cap, key):
    m0 = (NN == N) & (RG < K) & OWN
    si, xi = R.STOPS.index(sk), R.EXITS.index(xn)
    r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
    line = []
    for y in YRS:
        idx = np.where(m0 & YM[y])[0]
        o = idx[np.lexsort((key[idx], T[idx]))]
        busy, act, out = {}, [], []
        for i in o:
            kk = (SY[i], SD[i]); t = T[i]
            if busy.get(kk, 0) > t or r[i] != r[i]:
                continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == SD[i]) >= cap:
                continue
            end = t + int(j[i]) * 86400; busy[kk] = end; act.append((end, SD[i])); out.append(r[i])
        line.append(f"{np.mean(out):+.2f}R×{len(out)}")
    return " | ".join(line)
for cap in (6, 12):
    for nm, key in (("узкий диапазон первым", RG), ("сильный пробой первым", -BRK), ("спокойная монета первой", ATRP), ("дальше от EMA200 первой", -D200), ("ближе к EMA200 первой", D200)):
        print(f"лимит {cap:2d} · {nm:24s}: " + run(20, 2.5, 1.5, "dc20", cap, key))
