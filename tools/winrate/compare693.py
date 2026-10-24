"""the replay's virtual trades (the bot's code) vs the backtest list, trade by trade, 2026-01-10 .. 2026-10-10"""
import json, glob, numpy as np
A, B = 1780272000, 1791590400   # 2026-06-01 .. 2026-10-10
BL = [x for x in json.load(open("dlm_bt_v691b.json")) if A <= x["t"] < B]
bot, coins = [], set()
for f in sorted(glob.glob("replay693_[0-9].json")):
    d = json.load(open(f)); coins |= set(d["coins"]); bot += [t for t in d["trades"] if A <= t["t0"] < B and d["from"] <= t["t0"] < d["to"]]
BL = [x for x in BL if x["s"] in coins]
key_bl = {(x["s"], x["d"], x["c"], x["t"]): x for x in BL}
key_bot = {(t["symbol"], t["side"], {7200: "2h", 14400: "4h"}[t["bs"]], t["t0"]): t for t in bot}
both = set(key_bl) & set(key_bot); miss = sorted(set(key_bl) - set(key_bot), key=lambda k: k[3]); extra = sorted(set(key_bot) - set(key_bl), key=lambda k: k[3])
dr = [abs(key_bl[k]["r"] - key_bot[k]["r"]) for k in both if key_bot[k]["r"] is not None]
bad = [k for k in both if key_bot[k]["r"] is not None and abs(key_bl[k]["r"] - key_bot[k]["r"]) > 0.01]
print(f"монет {len(coins)}; бэктест {len(BL)} сделок, бот {len(bot)}; совпали {len(both)}, нет у бота {len(miss)}, лишние у бота {len(extra)}; "
      f"R расходится >0.01 у {len(bad)} (макс {max(dr) if dr else 0:.4f})")
import time
f = lambda k: time.strftime("%m-%d %H:%M", time.gmtime(k[3]))
for k in miss[:15]: print("  нет у бота:", k[0], k[1], k[2], f(k), key_bl[k]["k"], key_bl[k]["r"])
for k in extra[:15]: print("  лишняя у бота:", k[0], k[1], k[2], f(k), key_bot[k]["result"], key_bot[k]["r"])
for k in bad[:15]: print("  R:", k, key_bl[k]["r"], key_bot[k]["r"], key_bl[k]["k"], key_bot[k]["result"])
sb = sum(key_bl[k]["r"] for k in key_bl); sbot = sum(t["r"] for t in bot if t["r"] is not None)
print(f"сумма R: бэктест {sb:+.1f}, бот {sbot:+.1f}")
