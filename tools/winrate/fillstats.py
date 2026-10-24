"""how often the ⚡ orders fill after the scan, and when (the bot's own orders of the replays, 1h candles)"""
import os, json, glob, numpy as np, collections
os.environ["TFH"] = "4"
import s19h_engine as E1
from mk import ts
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"s23_4h/{c}.npz") or os.path.exists(f"s23_4hx/{c}.npz"): return c, scl
H1 = {}
def h1(gs):
    if gs not in H1:
        c, scl = bname(gs); T, O, H, L, C, V = E1.load15(c); H1[gs] = (T.astype(np.int64), H / scl, L / scl)
    return H1[gs]
OR = []; TR = []
for f in sorted(glob.glob("replay693_[0-9].json")):
    d = json.load(open(f)); OR += [o for o in d["orders"] if d["from"] <= o["t0"] < d["to"]]; TR += [t for t in d["trades"] if d["from"] <= t["t0"] < d["to"]]
tid = {t["id"] for t in TR}
st = collections.defaultdict(lambda: {"n": 0, "f": 0, "tr": 0, "h": collections.Counter(), "bars": collections.Counter()})
for o in OR:
    T, H, L = h1(o["symbol"]); i, j = int(np.searchsorted(T, o["t0"])), int(np.searchsorted(T, o["until"]))
    x = st[o["st"]]; x["n"] += 1
    for b in range(i, j):
        if (L[b] <= o["lv"]) if o["side"] > 0 else (H[b] >= o["lv"]):
            x["f"] += 1; hrs = int((T[b] - o["t0"]) // 3600); x["h"][hrs] += 1; x["bars"][hrs * 3600 // o["bs"] + 1] += 1
            x["tr"] += o["id"] in tid; break
for nm, x in st.items():
    bs = 7200 if nm == "close2h" else 14400
    print(f"{nm}: лимиток {x['n']}, исполнились {x['f']} ({x['f']/x['n']*100:.0f}%), из них стали сделками {x['tr']} ({x['tr']/max(x['f'],1)*100:.0f}%; "
          f"остальные — монета уже была в сделке / 20 в сторону)")
    print("   по свечам после выставления: " + ", ".join(f"{k}-я свеча {v/x['f']*100:.0f}%" for k, v in sorted(x["bars"].items())))
    cum = 0; parts = []
    for k in sorted(x["h"]): cum += x["h"][k]; parts.append((k + 1, cum / x["f"] * 100))
    print("   накопленно: " + ", ".join(f"за {h} ч {p:.0f}%" for h, p in parts if h in (1, 2, 4, 6, 8, 12, 16)))
# episodes: the orders of one coin & side (any stream) whose alive windows overlap or touch = one setup
by = collections.defaultdict(list)
for o in OR: by[(o["symbol"], o["side"])].append(o)
ne = nf = ntr = 0; per = []
for k, lst in by.items():
    lst.sort(key=lambda o: o["t0"]); ep = []
    for o in lst:
        if ep and o["t0"] <= max(x["until"] for x in ep): ep.append(o); continue
        if ep: per.append(ep)
        ep = [o]
    if ep: per.append(ep)
for ep in per:
    ne += 1; f = False
    for o in ep:
        T, H, L = h1(o["symbol"]); i, j = int(np.searchsorted(T, o["t0"])), int(np.searchsorted(T, o["until"]))
        if any(((L[b] <= o["lv"]) if o["side"] > 0 else (H[b] >= o["lv"])) for b in range(i, j)): f = True; break
    nf += f; ntr += any(o["id"] in tid for o in ep)
print(f"эпизодов (подряд идущие лимитки монеты в одну сторону = одна ситуация): {ne}, в среднем {len(OR)/ne:.1f} лимитки на эпизод; "
      f"цена дошла до лимитки в {nf} ({nf/ne*100:.0f}%), сделка была в {ntr} ({ntr/ne*100:.0f}% эпизодов, {ntr/max(nf,1)*100:.0f}% исполнившихся)")
