"""⚡ risk x the crowd at the entry: the accounts' long/short z (30d) x side high (the crowd already on the trade's side) -> less"""
exec(open("port_osc3.py").read().split('print("медиана wt')[0])
import ev2_engine as E2
from common import load as load1h
Gd = json.load(open("gh_dlm.json"))
lsz = np.full(len(PC), np.nan); cache = {}
for i, (p, g) in enumerate(zip(PC, Gd)):
    if not g: continue
    sym = g["sym"]
    if sym not in cache:
        a = load1h(sym); T = np.array([c["time"] for c in a], np.int64); M = E2.metrics(sym, T); cache[sym] = (T, E2.zs(M["ls_acc"], 24 * 30))
    T, z = cache[sym]; k = np.searchsorted(T, g["te"] - 3600, side="right") - 1
    if k >= 0: lsz[i] = z[k] * g["d"]
key2 = {(cid(p[5]["sym"]), round(float(p[0]))): lsz[i] for i, p in enumerate(PC)}
LS = np.array([key2.get((int(CID[i]), round(float(T0[i]))), np.nan) if MD[i] == 0 else np.nan for i in range(len(T0))])
q = np.nanquantile(LS[MD == 0], [0.2, 0.4, 0.6, 0.8]); print("пороги ls_z", q.round(2))
w704 = W_abs(-3, 22); U, RK = [1, 1, 1, 1], [4, 2, 1, 0.5]
stats2("v704", U, RK, w704)
for lo_m, hi_m in ((1.1, 0.8), (1.15, 0.85), (1.0, 0.75)):
    w = w704.copy(); ix = (MD == 0) & np.isfinite(LS); w[ix] *= np.where(LS[ix] <= q[1], lo_m, np.where(LS[ix] >= q[3], hi_m, 1.0))
    print("ср", (w[MD == 0] / w704[MD == 0]).mean().round(3), end=" "); stats2(f"толпа против ×{lo_m}, толпа в сторону сделки ×{hi_m}", U, RK, w)
