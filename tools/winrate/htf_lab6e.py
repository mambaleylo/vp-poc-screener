"""📏 HTF round 6 — the retrained models (htf_lab6m.py) on the bot's pipeline (htf_lab6s.py: both sides, the mirrored
walk). argv: <o variant> <n variant> [<s variant>] [chk] -> the longs (o OR n at q), the shorts by the s model."""
import sys
A = [a for a in sys.argv[1:] if a != "chk"]; CHK = "chk" in sys.argv
VO, VN = A[0], A[1]; VS = A[2] if len(A) > 2 else None
exec(open("htf_lab6s.py").read().split('CHK = "chk" in sys.argv; SD = 1')[0].replace("import sys\n", "", 1))   # -> src: htf_lab5 with the shorts
src = src.replace("Po, Pn = pct(SCo, THRo), pct(SCn, THRn)", """def pk(v):
    z = np.load(f"htf6_{v}.npz", allow_pickle=True); SC, PK, THR = z["SC"], z["PK"], z["THR"].item(); p = np.full(len(T), np.nan)
    for s, ref in THR.items():
        m = (PK == s) & np.isfinite(SC); rs = np.sort(ref)
        if m.any(): p[m] = np.searchsorted(rs, SC[m]) / len(rs)
    return p
Po, Pn = pk(VO), pk(VN); Ps = pk(VS) if VS else np.full(len(T), np.nan)""")
src = src.replace("cand0 = np.where(base & ((Po >= 0.98) | (Pn >= 0.99)))[0]", "cand0 = np.where(base & ((Po >= 0.99) | (Pn >= 0.99) | ((SIDE < 0) & (Ps >= 0.98))))[0]")
src = src.replace("base = HTF & (T >= ts(2023)) & (BOT if not CHK else ~BOT) & np.isfinite(Po) & ((SIDE < 0) | np.isfinite(Pn))",
                  "base = HTF & (T >= ts(2023)) & (BOT if not CHK else ~BOT) & (((SIDE > 0) & np.isfinite(Po) & np.isfinite(Pn)) | ((SIDE < 0) & np.isfinite(Ps)))")
src = src.replace("else (SIDE[cand0] < 0) & (Po[cand0] >= q)", "else (SIDE[cand0] < 0) & (Ps[cand0] >= q)")
exec(src)
SD = 1
print(f"== {VO} ИЛИ {VN} | монеты {'контрольные' if CHK else 'бота'} | кандидатов {len(cand0)}", flush=True)
for q in (0.997, 0.995, 0.993, 0.99): run(f"L{q} лонги q{q}", q=q, save=(q == 0.995 and not CHK))
if VS:
    SD = -1; bear50 = lambda c: ~BTC_UP[c]
    for q in (0.995, 0.99, 0.98):
        run(f"S{q} шорты ({VS}) q{q}", q=q, save=(q == 0.99 and not CHK)); run(f"S{q}b50 + BTC ниже SMA50", q=q, filt=bear50)
