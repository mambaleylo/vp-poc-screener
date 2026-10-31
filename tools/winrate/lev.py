exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "money200.py")).read().split('if __name__ == "__main__":')[0])
import collections
def simL(start, end, mode="cross", lev=10.0, eq0=200.0):
    E = eq0; opn = []; cut = 0; skip = 0; n = 0
    def close_to(t):
        nonlocal E
        opn.sort(key=lambda o: o[0])
        while opn and opn[0][0] <= t:
            o = opn.pop(0); E += o[1] * o[6]
    for t0, t1, r, st, sth, mod, coin in EV:
        if t0 < start: continue
        if t0 >= end: break
        close_to(t0)
        if any(o[4] == coin for o in opn): continue
        if mod == "dlm" and sum(1 for o in opn if o[5] == "dlm") >= 20: continue
        rd = E * RK[mod] / 100; hn = rd * sth / st; room = 0.9 * E - sum(o[2] for o in opn)
        if hn > room:
            if room < hn * 0.1: continue
            rd *= room / hn
        notional = rd / st
        mg = notional / lev if mode == "cross" else notional * (sth + 0.01)   # isolated: the liquidation just past the emergency stop
        free = E - sum(o[3] for o in opn); n += 1
        if mg > 0.9 * free:
            if free <= 1: skip += 1; continue
            k = 0.9 * free / mg; rd *= k; mg *= k; cut += 1
        opn.append((t1, rd, rd * sth / st, mg, coin, mod, r - (0.03 if mod != "dlm" else 0.0)))
    close_to(1e18)
    return E, cut, skip, n
S, Q = ts(2025, 10), ts(2026, 10)
starts = list(range(ts(2025, 1, 10), ts(2025, 9, 28) + 1, 7 * 86400))
for nm, kw in (("кросс 10x (сейчас)", dict(mode="cross", lev=10.0)), ("кросс 20x", dict(mode="cross", lev=20.0)), ("кросс 25x", dict(mode="cross", lev=25.0)),
               ("кросс 50x", dict(mode="cross", lev=50.0)), ("изолир., ликвидация сразу за аварийным стопом", dict(mode="iso"))):
    E, cut, skip, n = simL(S, Q, **kw)
    ys = np.array([simL(s, s + 365 * 86400, **kw)[0] for s in starts])
    print(f"{nm:48s} последние 12 мес с $200: ${E:>9,.0f} | урезано маржой {cut/n*100:3.0f}% сделок, пропущено {skip} | 38 стартов: 10% ${np.percentile(ys,10):>7,.0f} медиана ${np.median(ys):>8,.0f}")
