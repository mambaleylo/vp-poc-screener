exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "money200.py")).read().split('if __name__ == "__main__":')[0])
import json
def add_m(t, m):
    import time
    y, mo, d = time.gmtime(t)[:3]; mo += m; y += (mo - 1) // 12; mo = (mo - 1) % 12 + 1
    return calendar.timegm((y, mo, min(d, 28), 0, 0, 0))
END = max(v[1] for v in EV if v[5] == "dlm")
starts = list(range(ts(2025, 1, 10), ts(2025, 9, 28) + 1, 7 * 86400))
P = []
for s in starts:
    marks = [add_m(s, m) for m in range(1, 13)]
    E, out = sim(s, marks[-1], eq0=200.0, fr=True, marks=marks)
    P.append([200.0] + out)
P = np.array(P)
pct = {k: [round(float(np.percentile(P[:, m], q))) for m in range(13)] for k, q in (("p10", 10), ("p25", 25), ("p50", 50), ("p75", 75), ("p90", 90))}
print("окон", len(P)); [print(k, v) for k, v in pct.items()]
print("худший итог 12 мес", round(P[:, 12].min()), "лучший", round(P[:, 12].max()))
# the concrete paths
s1 = ts(2025, 1, 10); mk1 = [add_m(s1, m) for m in range(1, 21)]; E1, o1 = sim(s1, mk1[-1], eq0=200.0, fr=True, marks=mk1)
s2 = ts(2025, 10, 1); mk2 = [add_m(s2, m) for m in range(1, 13)]; E2, o2 = sim(s2, mk2[-1], eq0=200.0, fr=True, marks=mk2)
print("с янв.25:", [round(x) for x in o1]); print("с окт.25:", [round(x) for x in o2])
# the drop from a peak inside the windows (month marks)
dd = [float((1 - P[i] / np.maximum.accumulate(P[i])).max()) for i in range(len(P))]
print("просадка по месяцам: медиана", round(np.median(dd) * 100), "% худшая", round(max(dd) * 100), "%")
json.dump({"pct": pct, "jan25": [200.0] + o1, "oct25": [200.0] + o2, "n": len(P), "dd_med": float(np.median(dd)), "dd_max": float(max(dd)),
           "worst": float(P[:, 12].min()), "best": float(P[:, 12].max())}, open("path200.json", "w"))
