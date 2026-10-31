import sys; sys.argv = ["x", "20"]
src = open("money_exact.py").read().split('print("== реальные плечи монет')[0]
exec(src)
BASE_EV = list(EV)
def add(pat):
    out = []
    for fn in sorted(glob.glob(pat)):
        d_ = json.load(open(fn))
        for t in d_["trades"]:
            if t.get("status") != "CLOSED" or t.get("r") is None: continue
            t0 = int(t.get("t1h") or t["fbar"])
            if not (max(A, d_["from"]) <= t0 < min(B, d_["to"])): continue
            sth = abs(t["entry"] - (t.get("hsl") or t["sl"])) / t["entry"]; st = abs(t["entry"] - t["sl"]) / t["entry"]
            out.append({"t0": t0 + 3600, "t1": int(t["t_out"]), "r": float(t["r"]), "st": st, "sth": sth, "mod": "dlm", "sym": t["symbol"], "side": t["side"], "e": t["entry"]})
    return out
N150, N50 = add("rp_new150_*.json"), add("rp_new50_*.json")
for nm, extra in (("бот (210)", []), ("бот + новые от $150M", N150), ("бот + новые $50–150M", N50), ("бот + все новые", N150 + N50)):
    EV[:] = sorted(BASE_EV + extra, key=lambda v: v["t0"])
    for capx in (20.0, 125.0):
        E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(capx, real=True)
        print(f"{nm:24s} потолок {capx:>3.0f}x: ${E:>10,.0f} | сделок ⚡ в списке {sum(1 for v in EV if v['mod']=='dlm')} | урезано {cut}, пропущено {skip} (маржа {nfree}) | просадка {mdd*100:.0f}% | поддерж. маржа до {mmx*100:.0f}%, ликв. часов {liq} | мес: "
              + " ".join(f"{v:,.0f}" for k, v in sorted(mo.items())), flush=True)
