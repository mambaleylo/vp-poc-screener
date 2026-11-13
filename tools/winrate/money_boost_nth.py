"""«Режим разгона»: which of the day's ⚡ trades to take (the user: "если не первую, а вторую, или всегда только 3-ю в день"): the k-th
trade of the Moscow day by its fill (1st, 2nd, 3rd, the last, a random one), a $100 stake, the deployed sizing (isolated, the loss at
the emergency stop = the stake, the coin's leverage and the account's 20x cap — a trade that cannot take the whole stake is passed to
the next of the day). Per rule: the bets a week, the takes, $ a bet, $ a year, the worst run, by year; and 2023–24 against 2025–26
(a rule that is better only on one of them is chance). usage: python3 money_boost_nth.py [lab export .json.gz for the brackets]"""
import sys, gzip, json, time, collections, numpy as np
d = sorted(json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"], key=lambda x: x["f"])
br = json.load(gzip.open(sys.argv[1]))["bn_brackets"] if len(sys.argv) > 1 else {}
CAP, BUF, MSK, S = 20, 1.25, 3 * 3600, 100.0
def bsym(s):
    b = s.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in br: return c
def bet(x):
    """$ of the trade at the stake, or None when the whole stake does not fit"""
    e = x["e"]; em = abs(x["sl2"] - e) / e; notional = S / em; b = bsym(x["s"])
    if br and b:
        lmax = min(CAP, max((l for lim, l, m in br[b] if notional <= lim), default=0))
        if lmax < 1: return None
    return S * max(-1.0, x["d"] * (x["xp"] - e) / e / em) - 0.0005 * 2 * notional
days = collections.defaultdict(list)
for x in d:
    days[(x["f"] + MSK) // 86400].append(x)
rng = np.random.default_rng(3)
def pick(v, k):
    ok = [x for x in v if bet(x) is not None]
    if k == "last": return ok[-1] if ok else None
    if k == "rand": return ok[rng.integers(len(ok))] if ok else None
    return ok[k - 1] if len(ok) >= k else None
n_days = (d[-1]["f"] - d[0]["f"]) / 86400
print(f"дней с хотя бы одной сделкой ⚡: {len(days)}; сделок в такой день в среднем {np.mean([len(v) for v in days.values()]):.1f}, медиана {np.median([len(v) for v in days.values()]):.0f}")
print("правило | ставок в неделю | тейком | $ на ставку | $ в год | худшая серия $ | 2023–24: $ на ставку (ставок) | 2025–26 | по годам $")
for k in (1, 2, 3, 4, "last", "rand"):
    rows = []
    for day, v in sorted(days.items()):
        x = pick(v, k)
        if x is not None: rows.append((day, bet(x)))
    p = np.array([r for _, r in rows]); c = np.cumsum(p); dd = np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])
    yr = collections.defaultdict(float)
    for day, r in rows: yr[time.gmtime(day * 86400).tm_year] += r
    a = [r for day, r in rows if time.gmtime(day * 86400).tm_year <= 2024]; b = [r for day, r in rows if time.gmtime(day * 86400).tm_year >= 2025]
    nm = {1: "1-я сделка дня", 2: "2-я", 3: "3-я", 4: "4-я", "last": "последняя", "rand": "случайная"}[k]
    print(f"{nm:15s} | {len(p) / n_days * 7:4.1f} | {100 * (p > 0).mean():3.0f}% | {p.mean():+6.1f} | {p.sum() / n_days * 365:7,.0f} | {dd:5.0f} | "
          f"{np.mean(a):+6.1f} ({len(a)}) | {np.mean(b):+6.1f} ({len(b)}) | {dict((y, round(v_)) for y, v_ in sorted(yr.items()))}")
print("nth done")
