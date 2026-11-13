"""«Режим разгона» (the user: "если раз в неделю брать рандомную сделку по лимиткам и заходить в неё на весь депозит или 50%"):
once a week one random ⚡ trade of that week (the backtest list, 2023-01 .. 2026-09, its R as the bot's rules make it) taken with a
risk of f of the whole account — the stop costs f x |R| of the deposit (f = 1: the stop takes everything). The account starts at
$100, a year (52 weeks) from every week of the list as the start, 2000 random draws each -> the bad / usual / good year, the chance
to lose everything, to double. Compared with the bot's ⚡ itself (4% a trade, every trade) — the header's numbers.
usage: python3 money_boost.py"""
import json, numpy as np
BT = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"]
W = 7 * 86400
t = np.array([x["t"] for x in BT]); r = np.array([x["r"] for x in BT]); w = (t - t.min()) // W
weeks = [r[w == k] for k in range(int(w.max()) + 1)]
stop_pct = np.median([abs(x["sl"] - x["e"]) / x["e"] * 100 for x in BT])
rng = np.random.default_rng(7)
print(f"сделок {len(r)}, недель {len(weeks)}, из них без сделок {sum(1 for x in weeks if not len(x))}; WR {100 * (r > 0).mean():.0f}%, "
      f"средний R {r.mean():+.2f}, при выигрыше {r[r > 0].mean():+.2f}R, при проигрыше {r[r < 0].mean():+.2f}R; стоп в среднем {stop_pct:.1f}% от цены")
print("\nдоля счёта под риском | год со $100: плохой (10%) · обычный (50%) · хороший (90%) | счёт обнулён (< $1) | ×2 и больше | ×10 и больше")
for f in (1.0, 0.5, 0.25, 0.1, 0.04):
    fin = []
    for s in range(0, len(weeks) - 52):
        for _ in range(2000 // (len(weeks) - 52) + 1):
            eq = 100.0
            for k in range(s, s + 52):
                if len(weeks[k]):
                    eq *= max(0.0, 1 + f * float(rng.choice(weeks[k])))
                    if eq < 1:
                        eq = 0.0; break
            fin.append(eq)
    fin = np.array(fin); q = np.quantile(fin, (0.1, 0.5, 0.9))
    print(f"{f * 100:5.0f}% | ${q[0]:,.0f} · ${q[1]:,.0f} · ${q[2]:,.0f} | {100 * (fin < 1).mean():.0f}% | {100 * (fin >= 200).mean():.0f}% | {100 * (fin >= 1000).mean():.0f}%")
# all-in with leverage: the whole deposit as the margin at L x -> the stop costs L x stop% of the deposit
print(f"\n«весь депозит маржой с плечом L»: стоп ({stop_pct:.1f}% цены) стоит L × {stop_pct:.1f}% депозита — при плече ≥ {100 / stop_pct:.0f} "
      f"первый же стоп (или ликвидация раньше него) забирает весь счёт")
print("money_boost done")
