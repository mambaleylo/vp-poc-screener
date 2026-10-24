"""SMC / EMA live entry vs the backtest: the bot sees a touch by Gate's last price (10 s polls) or Binance's 1m wick (after
that minute closed) and enters at the MARKET — the backtest fills at the level. On 1m (40 coins, the honest lists with the
4h close stop): the entry = the level if the touch minute closed through it (the price stayed there — the poll sees it
at the level or better: the level taken), else the next minute's open (the wick seen late, the price bounced); "late"
(> 1R worse) -> no trade; the position sized by the real distance to the stop: R = the move / that distance"""
exec(open("m1_cstop.py").read().split("def m1(")[0])
def run(mod, hard_x):
    rows = []; late = 0; n = 0
    for tr in B[mod]:
        if tr.get("r") is None: continue
        c_, scl = bsym(tr["s"])
        if not c_ or tr["t"] < ts(2024, 10) + 86400: continue
        t, o, h, l, c = M1[c_]
        s = tr["d"]; e = tr["e"] * scl; sl = tr["sl"] * scl; tp = tr["tp"] * scl; risk0 = abs(e - sl)
        i0 = int(np.searchsorted(t, tr["t"])); i1 = int(np.searchsorted(t, tr["t"] + 3600))
        if i0 >= len(t) or t[i0] - tr["t"] > 600: continue
        k0 = next((k for k in range(i0, i1) if ((l[k] <= e) if s > 0 else (h[k] >= e))), -1)
        if k0 < 0 or k0 + 1 >= len(t): continue
        n += 1
        stayed = (c[k0] <= e) if s > 0 else (c[k0] >= e)
        ent = e if stayed else o[k0 + 1]
        if s * (ent - e) > risk0:
            late += 1; rows.append((tr["r"], 0.0, 0)); continue
        risk = abs(ent - sl); hs = e - s * hard_x * risk0
        pt = tr["pt"] * scl if tr.get("pt") else 0.0
        kk = k0 if stayed else k0 + 1
        if mod == "emx":
            R, k = walk(t, o, h, l, c, kk, s, ent, sl, hs, tp, pt, 0.33, tr["t"] + 3600, tr["t"] + 72 * 3600, 4, risk)
        else:
            R, k = walk(t, o, h, l, c, kk, s, ent, sl, hs, tp, 0.0, 0.0, 0, tr["t"] + 72 * 3600, 4, risk)
        rows.append((tr["r"], R, 1))
    a = np.array(rows)
    print(f"{mod}: касаний {n} · вход по уровню (цена осталась за уровнем) / после отскока · пропуск (хуже 1R): {late} | "
          f"список {a[:, 0].mean():+.3f}R · вживую {a[:, 1].mean():+.3f}R на касание (WR {np.mean(a[a[:, 2] > 0, 1] > 0)*100:.0f}%)", flush=True)
run("smc", 2.0); run("emx", 2.0)
def run_prv():
    rows = []; n = 0; late = 0
    for tr in B["prv"]:
        if tr.get("r") is None: continue
        c_, scl = bsym(tr["s"])
        t0 = tr.get("f") or tr["t"]
        if not c_ or t0 < ts(2024, 10) + 86400: continue
        t, o, h, l, c = M1[c_]
        s = tr["d"]; e = tr["e"] * scl; sl = tr["sl"] * scl; hs = tr["hs"] * scl; tp = tr["tp"] * scl; risk0 = abs(e - hs)
        i0 = int(np.searchsorted(t, t0)); i1 = int(np.searchsorted(t, t0 + 3600))
        if i0 >= len(t) or t[i0] - t0 > 600: continue
        k0 = next((k for k in range(i0, i1) if ((l[k] <= e) if s > 0 else (h[k] >= e))), -1)
        if k0 < 0 or k0 + 1 >= len(t): continue
        n += 1
        stayed = (c[k0] <= e) if s > 0 else (c[k0] >= e)
        ent = e if stayed else o[k0 + 1]
        risk = abs(ent - hs); kk = k0 if stayed else k0 + 1
        R, k = walk(t, o, h, l, c, kk, s, ent, sl, hs, tp, 0.0, 0.0, 0, (t0 // 3600) * 3600 + 48 * 3600, 1, risk)
        rows.append((tr["r"], R))
    a = np.array(rows)
    print(f"prv: касаний {n} | список {a[:, 0].mean():+.3f}R · вживую {a[:, 1].mean():+.3f}R (WR {np.mean(a[:, 1] > 0)*100:.0f}%)", flush=True)
run_prv()
