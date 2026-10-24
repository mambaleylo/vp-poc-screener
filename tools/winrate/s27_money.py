"""⚡ money: the deployed models (s26) vs the ones with the daily oscillators (s27), each stream and both, the v0.99.704 rules"""
exec(open("osc_take.py").read().split("run(\"v704: тейк 1.1 везде\"")[0])
def wt_of(evs):
    for e in evs:
        s_ = GH.dname(e["sym"].replace("USDT", "_USDT")) or (e["sym"] if os.path.exists(f"data/1h/{e['sym']}.csv") else None)
        if not s_: e["wt"] = np.nan; continue
        et, st_ = GH.coin(s_)["1d"]; k = np.searchsorted(et, e["key"][0], side="right") - 1
        e["wt"] = float(st_["wt"][k]) * e["s"] if k >= 60 else np.nan
    return evs
A4 = events3("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99)
A2 = events3("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99)
B4 = wt_of(events3("s23_4h", 2, "s27_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99))
B2 = wt_of(events3("s21h2", 0, "s27_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99))
wt_of(A4); wt_of(A2)
def runE(nm, evs):
    global E
    E = evs; run(nm, fx(1.1, 1.1))
runE("сейчас: 4ч s26 + 2ч s26", A4 + A2)
runE("4ч s27 + 2ч s26", B4 + A2)
runE("4ч s26 + 2ч s27", A4 + B2)
runE("4ч s27 + 2ч s27", B4 + B2)
