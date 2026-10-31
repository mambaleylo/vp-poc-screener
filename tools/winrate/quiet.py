exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "money200.py")).read().split('if __name__ == "__main__":')[0])
EV_ALL = list(EV)
def runs(mods, y0, y1):
    global EV
    EV = [v for v in EV_ALL if v[5] in mods]
    out = []
    for s in range(ts(y0, 1, 10), ts(y1, 1, 1), 7 * 86400):
        out.append(sim(s, s + 365 * 86400, eq0=200.0, fr=True)[0])
    EV = EV_ALL
    a = np.array(out); return len(a), [round(float(np.percentile(a, q))) for q in (10, 50, 90)], round(float(a.min()))
o4 = ("prv", "smc", "emx", "htf")
print("4 модуля без ⚡, старты 2023:", runs(o4, 2023, 2024))
print("4 модуля без ⚡, старты 2024:", runs(o4, 2024, 2025))
print("4 модуля без ⚡, старты янв–сен 2025:", runs(o4, 2025, 2025.75 and 2026) if False else None)
EV = [v for v in EV_ALL if v[5] in o4]
out = [sim(s, s + 365 * 86400, eq0=200.0, fr=True)[0] for s in range(ts(2025, 1, 10), ts(2025, 9, 28), 7 * 86400)]
EV = EV_ALL
a = np.array(out); print("4 модуля без ⚡, старты янв–сен 2025:", len(a), [round(float(np.percentile(a, q))) for q in (10, 50, 90)], round(float(a.min())))
