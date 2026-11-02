"""the ⚡ tab's history block (the user: "что вот это за данные? они… всегда одинаковые"): the model file's research.years / unseen
were the old research engines' (before v0.99.759) — re-counted on the streams the bot trades now: the lab's yearly walk-forward
orders of ⚡ 4h (_clr), 2h (_clr: the deployed recipe) and the shifted 4h (score >= 1.05 x the year's threshold), the bot's
exits; per year (2023-2026) the filled trades of the coins the models never trained on (the check coins + the bot's other ones)
and of the train coins: the count a month, R, WR, by stream; the whole and the last 12 months. -> research.years / unseen /
trades_pm in vp_dlm_model.json (the bot shows them). usage: dlm_research_card.py"""
import json, numpy as np
W = "/home/user/vp-lab-store/wf"; ts = lambda y, m=1: int(np.datetime64(f"{y}-{m:02d}-01", "s").astype(int)); END = ts(2026, 10)
rows = []
for nm, f, k in (("wick4h", "allorders_wick4h_clr", 1.0), ("close2h", "allorders_close2h_clr", 1.0), ("wick4h_o2", "allorders_wick4h_o2", 1.05)):
    z = np.load(f"{W}/{f}.npz", allow_pickle=True); m = z["filled"].astype(bool) & (z["score"] >= k * z["thr"]) & np.isfinite(z["R"])
    for t, r, g, c, sd, t1, to in zip(z["t"][m], z["R"][m], z["grp"][m].astype(str), z["coin"][m].astype(str), z["side"][m], z["t1h"][m], z["tout"][m]):
        rows.append((int(t), float(r), "train" if g == "train" else "unseen", nm, c, int(sd), int(t1), int(to)))
# the bot's pool: by the fill hour, a coin & side busy until its exit (any stream), at most 20 open a side
rows.sort(key=lambda x: (x[6], x[0])); busy = {}; act = []; kept = []
for x in rows:
    act = [a_ for a_ in act if a_[0] > x[6]]
    if busy.get((x[4], x[5]), 0) > x[6] or sum(1 for a_ in act if a_[1] == x[5]) >= 20: continue
    busy[(x[4], x[5])] = x[7]; act.append((x[7], x[5])); kept.append(x)
print(f"исполненных заявок {len(rows)}, сделок по правилам бота {len(kept)}"); rows = kept
t = np.array([x[0] for x in rows]); R = np.array([x[1] for x in rows]); G = np.array([x[2] for x in rows]); S = np.array([x[3] for x in rows])
out = {"train": {}, "unseen": {}}
for g in out:
    for Y in (2023, 2024, 2025, 2026):
        a, b = ts(Y), min(ts(Y + 1), END); mo = (b - a) / (30.44 * 86400); sel = (G == g) & (t >= a) & (t < b); r = R[sel]
        out[g][str(Y)] = {"n": int(len(r)), "avg": round(float(r.mean()), 3), "wr": round(float((r > 0).mean() * 100), 1), "pm": round(len(r) / mo, 1),
                          "streams": {s_: int((S[sel] == s_).sum()) for s_ in ("wick4h", "close2h", "wick4h_o2")}}
u = (G == "unseen") & (t >= ts(2023)); l12 = u & (t >= ts(2025, 10))
allm = (t >= ts(2023)) & (t < END); pm_all = allm.sum() / ((END - ts(2023)) / (30.44 * 86400)); pm12 = ((t >= ts(2025, 10)) & (t < END)).sum() / 12
un = {"wr": round(float((R[u] > 0).mean() * 100)), "avg": round(float(R[u].mean()), 3), "last12_wr": round(float((R[l12] > 0).mean() * 100)), "last12_avg": round(float(R[l12].mean()), 3)}
M = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); rs = M["research"]
rs["years"] = out; rs["unseen"] = un; rs["trades_pm"] = round(float(pm12)); rs["trades_pm_all"] = round(float(pm_all))
rs["years_src"] = "v0.99.765: the lab's yearly walk-forward of the streams the bot trades (4h, 2h, the shifted 4h at score >= 1.05 x thr), the bot's exits, 2023 - 2026-09 (tools/winrate dlm_research_card.py)"
rs["coins"] = 210
import collections
z = np.load(f"{W}/allorders_wick4h_clr.npz", allow_pickle=True); g_ = collections.Counter(dict(zip(z["coin"].astype(str), z["grp"].astype(str))).values())
rs["train_coins"] = g_["train"]; rs["check_coins"] = g_["check"]; rs["new_coins"] = g_["base"]
json.dump(M, open("/home/user/vp-poc-screener/vp_dlm_model.json", "w"), separators=(",", ":"))
for g in out:
    print(g, " · ".join(f"{Y}: {v['n']} ({v['pm']}/мес) {v['avg']:+.3f}R WR {v['wr']}%" for Y, v in out[g].items()))
print("невиданные монеты:", un, "· сделок в месяц: последние 12 мес", rs["trades_pm"], "· с 2023", rs["trades_pm_all"], "· монеты:", dict(g_))
