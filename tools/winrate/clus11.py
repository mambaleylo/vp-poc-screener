import os, numpy as np, time
src = open("listing.py").read(); src = src[:src.index("res = []\nfor D, G, S, T, H")]
exec(compile(src, "ls", "exec"))
src2 = open("clus.py").read(); exec(src2[:src2.index("# H13")])
for D, G, S, T, H in ((30, "any", 15, 1.5, 30), (30, "any", 15, 1.5, 14), (30, "down", 15, 1.5, 30), (3, "down", 15, 1.5, 14), (1, "any", 15, 1.5, 7), (30, "any", 25, 1.5, 30)):
    rows, crow, dif = [], [], []
    for s in NEW:
        if s not in DATA: continue
        tt, O, Hh, L, C, f = DATA[s]; t0 = tt[0]; tin = (t0 // HR) * HR + D * DAY
        if tin + H * DAY > tt[-1] + HR: continue
        first = C[min(23, len(C) - 1)]; j = np.searchsorted(tt, tin) - 1
        if j < 0 or (G == "up" and not C[j] > first) or (G == "down" and not C[j] < first): continue
        r = trade(s, tin, S, T, H)
        if r is None: continue
        rows.append((int(tin), r, -1))
        if CTRL.get(s):
            rc = trade(CTRL[s], tin, S, T, H)
            if rc is not None: crow.append((int(tin), rc, -1)); dif.append((int(tin), r - rc, -1))
    print(f"\nD{D} {G} S{S} T{T} H{H}:", flush=True)
    clus("  листинги, по месяцам", rows, "m"); clus("  контроль (старые монеты, те же часы)", crow, "m"); clus("  листинг минус контроль", dif, "m")
print("clus11 done", flush=True)
