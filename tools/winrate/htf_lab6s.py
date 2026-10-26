"""📏 HTF round 6 — shorts: the short touches of the HTF levels (model "o" only: the "n" model is long-only), the same
pipeline (reach filter, nearer first, cap 12 a side, one per coin), the mirrored walk (prices negated: the stop 1 dATR
above on a 4h close, hard 3 dATR, take 3R, 96 h); BTC regime filters (days closed before the touch); bot / check coins.
The control: the mirrored walk on the longs == the deployed list."""
import sys
src = open("htf_lab5.py").read().split('print("== база')[0]
src = src.replace("cand0 = np.where(base & ((Po >= 0.99) | (Pn >= 0.99)))[0]", "cand0 = np.where(base & ((Po >= 0.98) | (Pn >= 0.99)))[0]")
src = src.replace("base = HTF & (SIDE > 0) & (T >= ts(2023)) & BOT & np.isfinite(Po) & np.isfinite(Pn)",
                  "base = HTF & (T >= ts(2023)) & (BOT if not CHK else ~BOT) & np.isfinite(Po) & ((SIDE < 0) | np.isfinite(Pn))")
src = src.replace("    r0 = lv * datr / 100; fill = lv - depth * r0", "    r0 = abs(lv) * datr / 100; fill = lv - depth * r0")
src = src.replace("cost = (0.001 + 0.0003 * (q + 1) / 24) * fill / risk", "cost = (0.001 + 0.0003 * (q + 1) / 24) * abs(fill) / risk")
src = src.replace("- (0.001 + 0.0003 * (e - b0) / 24) * fill / risk, b0 - j + e - b0, 3, C[b], b0 - j", "- (0.001 + 0.0003 * (e - b0) / 24) * abs(fill) / risk, b0 - j + e - b0, 3, C[b], b0 - j")
src = src.replace('''def bars(k):
    if k not in BARS: BARS[k] = LE.load_np(Dd["names"][k])
    return BARS[k]''', '''def bars(k, sd=1):
    if (k, sd) not in BARS:
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        BARS[(k, sd)] = (Tb, O, H, L, C, V) if sd > 0 else (Tb, -O, -L, -H, -C, V)
    return BARS[(k, sd)]''')
src = src.replace("NEAR = (OPEN - LV) / (LV * DATR / 100)", "NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)")
src = src.replace("""    m = (Po[cand0] >= q) | (Pn[cand0] >= q)
    c = cand0[m]""", """    m = (SIDE[cand0] > 0) & ((Po[cand0] >= q) | (Pn[cand0] >= q)) if SD > 0 else (SIDE[cand0] < 0) & (Po[cand0] >= q)
    c = cand0[m]""")
src = src.replace("""        Tb, O, H, L, C, V = bars(k)
        for i in c[SYM[c] == k]:
            R[i] = walk(O, H, L, C, Tb, int(J[i]), float(LV[i]),""", """        Tb, O, H, L, C, V = bars(k, SD)
        for i in c[SYM[c] == k]:
            R[i] = walk(O, H, L, C, Tb, int(J[i]), float(SD * LV[i]),""")
src = src.replace('"e": fill / scl, "sl": (sb - r0) / scl, "hs": (sb - hard_a * r0) / scl,', '"e": fill / scl, "sl": (sb - SD * r0) / scl, "hs": (sb - SD * hard_a * r0) / scl, "d": SD,')
CHK = "chk" in sys.argv; SD = 1
exec(src)
print("== монеты", "контрольные" if CHK else "бота", "| кандидатов", len(cand0), flush=True)
SD = 1; run("L0 лонги как в боте (контроль)")
SD = -1
bear50 = lambda c: ~BTC_UP[c]; bear20 = lambda c: BTC_R20[c] < 0; bear20d = lambda c: BTC_R20[c] < -0.10
for q in (0.995, 0.99, 0.98):
    run(f"S{q} шорты q{q} все", q=q, save=not CHK and q == 0.99)
    run(f"S{q}b50 BTC ниже SMA50", q=q, filt=bear50, save=not CHK and q == 0.99)
    run(f"S{q}b20 BTC 20д < 0", q=q, filt=bear20)
    run(f"S{q}b20d BTC 20д < −10%", q=q, filt=bear20d)
for kw, nm in ((dict(take=2.0), "тейк 2R"), (dict(hold=48), "48ч"), (dict(kh=1), "стоп по 1ч"), (dict(hard_a=2.0), "аварийный 2")):
    run(f"S0.99b50x {nm}", q=0.99, filt=bear50, **kw)
