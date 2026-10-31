"""money from the bot's backtest lists (vp_bt_trades.json): ⚡ 4.5 + P/R 3 + SMC 2.5 + EMA 2 + HTF 2 (as deployed), the bot's own
rules — one position per coin, ⚡ <= 20 at once, the open risk at the exchange stops <= 90% of the equity (bn_heat_cap: scaled,
under a tenth -> skipped), cross 10x with <= 90% of the free margin; the result at the exit; friction -0.03R (not ⚡)"""
import json, calendar, numpy as np, sys
D = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
RK = {"dlm": 4.5, "prv": 3.0, "smc": 2.5, "emx": 2.0, "htf": 2.0}
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
EV = []
for mod, rk in RK.items():
    for t in D[mod]:
        e = t["e"]; st = max(0.002, abs(e - t["sl"]) / e)
        sth = max(st, abs(e - t.get("sl2", t.get("hs", t["sl"]))) / e)
        t0 = t["f"] if mod == "dlm" else t["t"]
        EV.append((t0, t["x"], t["r"], st, sth, mod, t["s"]))
EV.sort(key=lambda v: v[0])
def sim(start, end, eq0=100.0, fr=True, marks=()):
    E = eq0; opn = []; out = []; mi = 0; marks = list(marks)
    def close_to(t):
        nonlocal E
        opn.sort(key=lambda o: o[0])
        while opn and opn[0][0] <= t:
            x, rd, heat, mg, coin, mod, r = opn.pop(0); E += rd * r
    for t0, t1, r, st, sth, mod, coin in EV:
        if t0 < start: continue
        if t0 >= end: break
        while mi < len(marks) and marks[mi] <= t0:
            close_to(marks[mi]); out.append(E); mi += 1
        close_to(t0)
        if E <= 1: break
        if any(o[4] == coin for o in opn): continue
        if mod == "dlm" and sum(1 for o in opn if o[5] == "dlm") >= 20: continue
        rd = E * RK[mod] / 100; hn = rd * sth / st; room = 0.9 * E - sum(o[2] for o in opn)
        if hn > room:
            if room < hn * 0.1: continue
            rd *= room / hn
        mg = rd / st / 10; free = E - sum(o[3] for o in opn)
        if mg > 0.9 * free:
            if free <= 1: continue
            rd *= 0.9 * free / mg; mg = rd / st / 10
        opn.append((t1, rd, rd * sth / st, mg, coin, mod, r - (0.03 if (fr and mod != "dlm") else 0.0)))
    while mi < len(marks):
        close_to(marks[mi]); out.append(E); mi += 1
    close_to(1e18)
    return E, out
if __name__ == "__main__":
    for fr in (False, True):
        print("издержки" if fr else "как в бэктесте", "| последние 12 мес (окт.25 → окт.26) с $100:", round(sim(ts(2025, 10), ts(2026, 10), fr=fr)[0]))
