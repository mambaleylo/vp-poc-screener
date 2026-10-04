#!/usr/bin/env python3
"""Большая проверка торговых сетапов: Smart Money, зоны интереса, классика — на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python setup_scan.py [число монет, по умолчанию 60]
    python setup_scan.py 60 --skip 60      # совсем другие монеты (с 61-й по 120-ю)
    python setup_scan.py 60 --skip 60 --check "13:4h,6:1h"   # только заранее выбранные сетапы (номер:ТФ)

Ничего не торгует. Свечи 15м (~100 дней), 1ч (~400 дней), 4ч (~4 года),
кэшируются тем же кэшем, что у бота. Первый запуск 10-20 минут.

СЕТАПЫ (правила заданы заранее, сигнал по закрытию свечи, вход — открытие следующей):
 SMC:  1 FVG-ретест · 2 ордерблок-ретест · 3 снятие ликвидности (вынос 20-свечного
       экстремума и возврат) · 4 BOS (пробой свинга) · 5 CHoCH (слом тренда) ·
       6 снятие равных минимумов/максимумов
 ЗОНЫ: 7 спрос/предложение (база перед импульсом, первый ретест) · 8 вынос
       PDH/PDL (максимума/минимума прошлого дня) с возвратом · 9 пробой прошлой
       недели · 10 discount/premium + поглощение · 15 вынос азиатской сессии
 КЛАССИКА: 11 поглощение на 20-свечном экстремуме · 12 пробой внутренней свечи ·
       13 дивергенция RSI · 14 пробой после сжатия Боллинджера · 16 откат к EMA50 по тренду
ВЫХОД: стоп 1.5 ATR, тейк 1R / 2R / 3R, максимум 48 свечей. Комиссия 0.1% за круг.

ЧЕСТНОСТЬ (около 140 проверок сразу — без этого «найдётся» случайность):
 - монеты делятся пополам: ПОИСК (чётные по объёму) и ПОДТВЕРЖДЕНИЕ (нечётные);
 - каждая сделка сравнивается со случайными входами на той же монете, ТФ,
   стороне и с тем же стопом/тейком: превышение = R сделки минус R случайного входа;
 - t считается по дням (монеты движутся вместе);
 - на поиске отбор с поправкой на число проверок (Бенджамини-Хохберг, 10%)
   и плюс в обеих половинах периода;
 - отобранное проверяется на монетах подтверждения: превышение > 0, t >= 2,
   и сама сделка в плюсе. Только это считается рабочим.
"""
import importlib.util
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")

TFS = {"15m": 100, "1h": 400, "4h": 1500}
RRS = (1.0, 2.0, 3.0)
STOP_ATR = 1.5
MAX_HOLD = 48
FEE = 0.001
COOLDOWN = 5
BASE_SAMPLES = 150
FDR_Q = 0.10
CONFIRM_T = 2.0
OUT = []
CHECK = None   # --check "13:4h,6:1h" -> {"13": {"4h"}, "6": {"1h"}}


def say(s=""):
    print(s)
    OUT.append(s)


# ---------------------------------------------------------------- indicators

def atr_series(c, n=14):
    out, prev = [None] * len(c), None
    for i in range(1, len(c)):
        tr = max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]), abs(c[i]["low"] - c[i - 1]["close"]))
        prev = tr if prev is None else (prev * (n - 1) + tr) / n
        out[i] = prev if i >= n else None
    return out


def ema(xs, n):
    out, k, v = [], 2 / (n + 1), None
    for x in xs:
        v = x if v is None else v + k * (x - v)
        out.append(v)
    return out


def rsi_series(xs, n=14):
    out, up, dn = [None] * len(xs), None, None
    for i in range(1, len(xs)):
        g, l_ = max(xs[i] - xs[i - 1], 0), max(xs[i - 1] - xs[i], 0)
        up = g if up is None else (up * (n - 1) + g) / n
        dn = l_ if dn is None else (dn * (n - 1) + l_) / n
        if i >= n:
            out[i] = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    return out


def pivots(H, L, k):
    """confirmed swing points: (index of pivot, index when it becomes known)"""
    ph, pl = [], []
    for p in range(k, len(H) - k):
        if H[p] == max(H[p - k:p + k + 1]):
            ph.append((p, p + k))
        if L[p] == min(L[p - k:p + k + 1]):
            pl.append((p, p + k))
    return ph, pl


# ---------------------------------------------------------------- setups
# each: f(ctx) -> list of (i, side); signal at the close of bar i

def s_fvg(x):
    c, A, out = x["c"], x["atr"], []
    n = len(c)
    for g in range(2, n - 1):
        if not A[g]:
            continue
        for side in (1, -1):
            if side > 0:
                lo, hi = c[g - 2]["high"], c[g]["low"]
            else:
                lo, hi = c[g]["high"], c[g - 2]["low"]
            if hi - lo < 0.3 * A[g]:
                continue
            for i in range(g + 1, min(g + 21, n)):
                b = c[i]
                if side > 0:
                    if b["close"] < lo:
                        break
                    if b["low"] <= hi:
                        out.append((i, 1))
                        break
                else:
                    if b["close"] > hi:
                        break
                    if b["high"] >= lo:
                        out.append((i, -1))
                        break
    return out


def s_orderblock(x):
    c, A, out = x["c"], x["atr"], []
    n = len(c)
    for d in range(11, n - 1):
        if not A[d]:
            continue
        body = c[d]["close"] - c[d]["open"]
        if abs(body) < 1.5 * A[d]:
            continue
        side = 1 if body > 0 else -1
        if side > 0 and c[d]["close"] <= max(b["high"] for b in c[d - 10:d]):
            continue
        if side < 0 and c[d]["close"] >= min(b["low"] for b in c[d - 10:d]):
            continue
        ob = next((j for j in range(d - 1, d - 6, -1)
                   if (c[j]["close"] < c[j]["open"]) == (side > 0) and c[j]["close"] != c[j]["open"]), None)
        if ob is None:
            continue
        lo, hi = c[ob]["low"], c[ob]["high"]
        for i in range(d + 1, min(d + 31, n)):
            b = c[i]
            if side > 0:
                if b["close"] < lo:
                    break
                if b["low"] <= hi:
                    out.append((i, 1))
                    break
            else:
                if b["close"] > hi:
                    break
                if b["high"] >= lo:
                    out.append((i, -1))
                    break
    return out


def s_sweep(x):
    c, out = x["c"], []
    H, L = x["H"], x["L"]
    for i in range(20, len(c)):
        lo, hi = min(L[i - 20:i]), max(H[i - 20:i])
        if L[i] < lo and c[i]["close"] > lo:
            out.append((i, 1))
        elif H[i] > hi and c[i]["close"] < hi:
            out.append((i, -1))
    return out


def s_bos(x):
    c, H, L, out = x["c"], x["H"], x["L"], []
    ph, pl = x["ph5"], x["pl5"]
    hi_i = lo_i = 0
    last_h = last_l = None
    for i in range(1, len(c)):
        while hi_i < len(ph) and ph[hi_i][1] <= i:
            last_h = H[ph[hi_i][0]]
            hi_i += 1
        while lo_i < len(pl) and pl[lo_i][1] <= i:
            last_l = L[pl[lo_i][0]]
            lo_i += 1
        cl, pc = c[i]["close"], c[i - 1]["close"]
        if last_h is not None and cl > last_h >= pc:
            out.append((i, 1))
        elif last_l is not None and cl < last_l <= pc:
            out.append((i, -1))
    return out


def s_choch(x):
    c, H, L, out = x["c"], x["H"], x["L"], []
    ph, pl = x["ph5"], x["pl5"]
    hs, ls = [], []
    hi_i = lo_i = 0
    for i in range(1, len(c)):
        while hi_i < len(ph) and ph[hi_i][1] <= i:
            hs.append(H[ph[hi_i][0]])
            hi_i += 1
        while lo_i < len(pl) and pl[lo_i][1] <= i:
            ls.append(L[pl[lo_i][0]])
            lo_i += 1
        if len(hs) < 2 or len(ls) < 2:
            continue
        cl, pc = c[i]["close"], c[i - 1]["close"]
        down = hs[-1] < hs[-2] and ls[-1] < ls[-2]
        up = hs[-1] > hs[-2] and ls[-1] > ls[-2]
        if down and cl > hs[-1] >= pc:
            out.append((i, 1))
        elif up and cl < ls[-1] <= pc:
            out.append((i, -1))
    return out


def s_equal_sweep(x):
    c, A, H, L, out = x["c"], x["atr"], x["H"], x["L"], []
    ph, pl = x["ph3"], x["pl3"]
    hs, ls = [], []
    hi_i = lo_i = 0
    for i in range(1, len(c)):
        while hi_i < len(ph) and ph[hi_i][1] <= i:
            hs.append(H[ph[hi_i][0]])
            hi_i += 1
        while lo_i < len(pl) and pl[lo_i][1] <= i:
            ls.append(L[pl[lo_i][0]])
            lo_i += 1
        if not A[i]:
            continue
        if len(ls) >= 2 and abs(ls[-1] - ls[-2]) <= 0.15 * A[i]:
            lvl = min(ls[-1], ls[-2])
            if L[i] < lvl < c[i]["close"]:
                out.append((i, 1))
                ls.append(L[i])   # level consumed
                continue
        if len(hs) >= 2 and abs(hs[-1] - hs[-2]) <= 0.15 * A[i]:
            lvl = max(hs[-1], hs[-2])
            if H[i] > lvl > c[i]["close"]:
                out.append((i, -1))
                hs.append(H[i])
    return out


def s_supply_demand(x):
    c, A, out = x["c"], x["atr"], []
    n = len(c)
    for d in range(2, n - 1):
        if not A[d]:
            continue
        body = c[d]["close"] - c[d]["open"]
        base = c[d - 1]
        if abs(body) < 2 * A[d] or abs(base["close"] - base["open"]) > 0.5 * A[d]:
            continue
        side = 1 if body > 0 else -1
        if side > 0:
            lo, hi = base["low"], max(base["open"], base["close"])
        else:
            lo, hi = min(base["open"], base["close"]), base["high"]
        for i in range(d + 2, min(d + 51, n)):
            b = c[i]
            if side > 0:
                if b["close"] < lo:
                    break
                if b["low"] <= hi:
                    out.append((i, 1))
                    break
            else:
                if b["close"] > hi:
                    break
                if b["high"] >= lo:
                    out.append((i, -1))
                    break
    return out


def _period_levels(c, period):
    """previous period's high/low known at each bar"""
    out = [None] * len(c)
    cur_key, cur_h, cur_l, prev = None, None, None, None
    for i, b in enumerate(c):
        k = (b["time"] + (3 * 86400 if period == 7 * 86400 else 0)) // period
        if k != cur_key:
            if cur_key is not None:
                prev = (cur_h, cur_l)
            cur_key, cur_h, cur_l = k, b["high"], b["low"]
        else:
            cur_h, cur_l = max(cur_h, b["high"]), min(cur_l, b["low"])
        out[i] = (prev, k)
    return out


def s_pd_sweep(x):
    if x["tf"] == "4h":
        return []
    c, out, used = x["c"], [], set()
    for i, (lv, k) in enumerate(x["pd"]):
        if not lv:
            continue
        ph, pl = lv
        b = c[i]
        if b["low"] < pl < b["close"] and (k, 1) not in used:
            out.append((i, 1))
            used.add((k, 1))
        elif b["high"] > ph > b["close"] and (k, -1) not in used:
            out.append((i, -1))
            used.add((k, -1))
    return out


def s_week_break(x):
    c, out, used = x["c"], [], set()
    for i, (lv, k) in enumerate(x["pw"]):
        if not lv or i == 0:
            continue
        ph, pl = lv
        if c[i]["close"] > ph >= c[i - 1]["close"] and (k, 1) not in used:
            out.append((i, 1))
            used.add((k, 1))
        elif c[i]["close"] < pl <= c[i - 1]["close"] and (k, -1) not in used:
            out.append((i, -1))
            used.add((k, -1))
    return out


def _engulf(c, i):
    a, b = c[i - 1], c[i]
    if a["close"] < a["open"] and b["close"] > b["open"] and b["close"] >= a["open"] and b["open"] <= a["close"]:
        return 1
    if a["close"] > a["open"] and b["close"] < b["open"] and b["close"] <= a["open"] and b["open"] >= a["close"]:
        return -1
    return 0


def s_discount_engulf(x):
    c, H, L, out = x["c"], x["H"], x["L"], []
    for i in range(50, len(c)):
        e = _engulf(c, i)
        if not e:
            continue
        hi, lo = max(H[i - 50:i]), min(L[i - 50:i])
        if hi <= lo:
            continue
        pos = (c[i]["close"] - lo) / (hi - lo)
        if e > 0 and pos < 0.25:
            out.append((i, 1))
        elif e < 0 and pos > 0.75:
            out.append((i, -1))
    return out


def s_engulf_extreme(x):
    c, H, L, out = x["c"], x["H"], x["L"], []
    for i in range(20, len(c)):
        e = _engulf(c, i)
        if e > 0 and min(L[i - 1], L[i]) <= min(L[i - 20:i + 1]):
            out.append((i, 1))
        elif e < 0 and max(H[i - 1], H[i]) >= max(H[i - 20:i + 1]):
            out.append((i, -1))
    return out


def s_inside_break(x):
    c, out = x["c"], []
    for i in range(2, len(c)):
        m, ib = c[i - 2], c[i - 1]
        if not (ib["high"] <= m["high"] and ib["low"] >= m["low"]):
            continue
        if c[i]["close"] > m["high"]:
            out.append((i, 1))
        elif c[i]["close"] < m["low"]:
            out.append((i, -1))
    return out


def s_rsi_div(x):
    c, R, H, L, out = x["c"], x["rsi"], x["H"], x["L"], []
    ph, pl = x["ph3"], x["pl3"]
    for a, b in zip(pl, pl[1:]):
        p1, p2 = a[0], b[0]
        if R[p1] is None or R[p2] is None or p2 - p1 > 40:
            continue
        if L[p2] < L[p1] and R[p2] > R[p1] and R[p1] < 35:
            out.append((b[1], 1))
    for a, b in zip(ph, ph[1:]):
        p1, p2 = a[0], b[0]
        if R[p1] is None or R[p2] is None or p2 - p1 > 40:
            continue
        if H[p2] > H[p1] and R[p2] < R[p1] and R[p1] > 65:
            out.append((b[1], -1))
    return [(i, s) for i, s in out if i < len(c)]


def s_bb_squeeze(x):
    c, out = x["c"], []
    cl = x["cl"]
    n = len(c)
    bw, up, dn = [None] * n, [None] * n, [None] * n
    for i in range(19, n):
        w = cl[i - 19:i + 1]
        mu = sum(w) / 20
        sd = math.sqrt(sum((v - mu) ** 2 for v in w) / 20)
        up[i], dn[i] = mu + 2 * sd, mu - 2 * sd
        bw[i] = 4 * sd / mu if mu else None
    for i in range(140, n):
        hist = sorted(v for v in bw[i - 120:i] if v is not None)
        if len(hist) < 60:
            continue
        thr = hist[len(hist) // 10]
        if not any(bw[j] is not None and bw[j] <= thr for j in range(i - 5, i)):
            continue
        if cl[i] > up[i] and cl[i - 1] <= up[i - 1]:
            out.append((i, 1))
        elif cl[i] < dn[i] and cl[i - 1] >= dn[i - 1]:
            out.append((i, -1))
    return out


def s_asia_sweep(x):
    if x["tf"] not in ("15m", "1h"):
        return []
    c, out = x["c"], []
    day, a_hi, a_lo, done = None, None, None, set()
    for i, b in enumerate(c):
        d, hr = b["time"] // 86400, (b["time"] % 86400) // 3600
        if d != day:
            day, a_hi, a_lo = d, None, None
        if hr < 7:
            a_hi = b["high"] if a_hi is None else max(a_hi, b["high"])
            a_lo = b["low"] if a_lo is None else min(a_lo, b["low"])
            continue
        if hr >= 12 or a_hi is None:
            continue
        if b["low"] < a_lo < b["close"] and (d, 1) not in done:
            out.append((i, 1))
            done.add((d, 1))
        elif b["high"] > a_hi > b["close"] and (d, -1) not in done:
            out.append((i, -1))
            done.add((d, -1))
    return out


def s_ema_pullback(x):
    c, e50, e200, out = x["c"], x["e50"], x["e200"], []
    for i in range(210, len(c)):
        b = c[i]
        if e50[i] > e200[i] and e50[i] > e50[i - 10] and b["low"] <= e50[i] < b["close"]:
            out.append((i, 1))
        elif e50[i] < e200[i] and e50[i] < e50[i - 10] and b["high"] >= e50[i] > b["close"]:
            out.append((i, -1))
    return out


SETUPS = [
    ("1 FVG-ретест", s_fvg), ("2 ордерблок", s_orderblock), ("3 снятие ликвидности", s_sweep),
    ("4 BOS пробой свинга", s_bos), ("5 CHoCH слом тренда", s_choch), ("6 снятие равных экстр.", s_equal_sweep),
    ("7 спрос/предложение", s_supply_demand), ("8 вынос PDH/PDL", s_pd_sweep), ("9 пробой прошлой недели", s_week_break),
    ("10 discount+поглощение", s_discount_engulf), ("11 поглощение на экстр.", s_engulf_extreme),
    ("12 пробой внутр. свечи", s_inside_break), ("13 дивергенция RSI", s_rsi_div),
    ("14 сжатие Боллинджера", s_bb_squeeze), ("15 вынос Азии", s_asia_sweep), ("16 откат к EMA50", s_ema_pullback),
]


# ---------------------------------------------------------------- trades

def bracket(c, k, side, stop_d, rr):
    """enter at open of bar k; stop first if both touched; R net of fees"""
    e = c[k]["open"]
    sl, tp = e - side * stop_d, e + side * stop_d * rr
    end = min(k + MAX_HOLD, len(c)) - 1
    px = c[end]["close"]
    for j in range(k, end + 1):
        b = c[j]
        if (side > 0 and b["low"] <= sl) or (side < 0 and b["high"] >= sl):
            px = sl
            break
        if (side > 0 and b["high"] >= tp) or (side < 0 and b["low"] <= tp):
            px = tp
            break
    return side * (px - e) / stop_d - FEE * e / stop_d


def make_ctx(c, tf):
    H = [b["high"] for b in c]
    L = [b["low"] for b in c]
    cl = [b["close"] for b in c]
    ph5, pl5 = pivots(H, L, 5)
    ph3, pl3 = pivots(H, L, 3)
    return {"c": c, "tf": tf, "H": H, "L": L, "cl": cl, "atr": atr_series(c), "rsi": rsi_series(cl),
            "e50": ema(cl, 50), "e200": ema(cl, 200), "ph5": ph5, "pl5": pl5, "ph3": ph3, "pl3": pl3,
            "pd": _period_levels(c, 86400), "pw": _period_levels(c, 7 * 86400)}


def run_series(c, tf, rng):
    """-> {(setup, tf, rr): [(time, raw R, excess R)]}"""
    x = make_ctx(c, tf)
    A = x["atr"]
    n = len(c)
    ok = [i for i in range(20, n - MAX_HOLD - 1) if A[i]]
    if len(ok) < 200:
        return {}
    base = {}
    for side in (1, -1):
        idx = [rng.choice(ok) for _ in range(BASE_SAMPLES)]
        for rr in RRS:
            rs = [bracket(c, i + 1, side, STOP_ATR * A[i], rr) for i in idx]
            base[(side, rr)] = sum(rs) / len(rs)
    res = {}
    for name, fn in SETUPS:
        if CHECK is not None and tf not in CHECK.get(name.split()[0], ()):
            continue
        try:
            sigs = sorted(set(fn(x)))
        except Exception as e:
            print(f"  ошибка сетапа {name}: {e}")
            continue
        last = {1: -10 ** 9, -1: -10 ** 9}
        for i, side in sigs:
            if i >= n - MAX_HOLD - 1 or i < 20 or not A[i] or i - last[side] < COOLDOWN:
                continue
            last[side] = i
            for rr in RRS:
                r = bracket(c, i + 1, side, STOP_ATR * A[i], rr)
                res.setdefault((name, tf, rr), []).append((c[i]["time"], r, r - base[(side, rr)]))
    return res


# ---------------------------------------------------------------- stats

def day_t(rows, k=2):
    d = {}
    for r in rows:
        d.setdefault(r[0] // 86400, []).append(r[k])
    xs = [sum(v) / len(v) for v in d.values()]
    n = len(xs)
    if n < 10:
        return None, n
    mu = sum(xs) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in xs) / (n - 1))
    return (mu / (sd / math.sqrt(n)) if sd > 0 else None), n


def p_one_sided(t):
    return 0.5 * math.erfc(t / math.sqrt(2)) if t is not None else 1.0


def stats(rows):
    rows = sorted(rows)
    n = len(rows)
    t, days = day_t(rows)
    half = n // 2
    return {"n": n, "days": days, "raw": sum(r[1] for r in rows) / n, "ex": sum(r[2] for r in rows) / n, "t": t,
            "h1": sum(r[2] for r in rows[:half]) / max(half, 1), "h2": sum(r[2] for r in rows[half:]) / max(n - half, 1),
            "wr": sum(1 for r in rows if r[1] > 0) / n * 100, "span": (rows[-1][0] - rows[0][0]) / 86400 if n > 1 else 1}


def collect(m, syms, now, rng, label):
    agg = {}
    t0 = time.time()
    for k, s in enumerate(syms, 1):
        for tf, days in TFS.items():
            if CHECK is not None and not any(tf in v for v in CHECK.values()):
                continue
            try:
                cs = m.get_candles_range(s, tf, now - days * 86400, now) or []
                sec = m.INTERVAL_SECONDS.get(tf, 3600)
                cs = [b for b in cs if b["time"] + sec <= now]
            except Exception as e:
                print(f"  {s} {tf}: {e}")
                continue
            if len(cs) < 400:
                continue
            for key, rows in run_series(cs, tf, rng).items():
                agg.setdefault(key, []).extend(rows)
        print(f"  {label}: {k}/{len(syms)} монет ({time.time() - t0:.0f} с)")
    return agg


def fmt(name, tf, rr, s, n_coins):
    td = "—" if s["t"] is None else f"{s['t']:+.2f}"
    per_day = s["n"] / max(s["span"], 1) / max(n_coins, 1)
    return (f"  {name:<24} {tf:>3} RR{rr:g}: n={s['n']:5d} (~{per_day:.2f}/день на монету) WR {s['wr']:3.0f}% · "
            f"сделка {s['raw']:+.3f}R · превыш. {s['ex']:+.3f}R · t={td} · половины {s['h1']:+.3f}/{s['h2']:+.3f}")


def check_mode(m, syms, skip, spec_txt):
    """Pre-chosen setups only (e.g. a near-miss of a previous search), on
    a coin set of your choice — one hypothesis each, no search, so no
    multiple-testing correction: needs excess > 0, t >= 2 and a positive
    trade, and positive excess in both halves."""
    global CHECK
    CHECK = {}
    for part in spec_txt.split(","):
        num, tf = part.strip().split(":")
        CHECK.setdefault(num, set()).add(tf)
    now = int(time.time())
    t0 = time.time()
    say(f"ПРОВЕРКА {spec_txt} на монетах с {skip + 1}-й по {skip + len(syms)}-ю ({len(syms)} шт.)")
    agg = collect(m, syms, now, random.Random(11), "проверка")
    good = []
    for key in sorted(agg):
        s = stats(agg[key])
        ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["raw"] > 0 and s["h1"] > 0 and s["h2"] > 0
        say(fmt(*key, s, len(syms)) + ("  ✓ ПОДТВЕРДИЛСЯ" if ok else ""))
        if ok:
            good.append(key)
    say(f"\nИТОГ: {'подтвердились — ' + '; '.join(f'{k[0]} {k[1]} RR{k[2]:g}' for k in good) if good else 'не подтвердился ни один'}"
        f" (нужно: сделка в плюсе, превышение над случайным > 0 и t >= {CONFIRM_T}, плюс в обеих половинах)")
    say(f"время: {time.time() - t0:.0f} с")
    with open(os.path.join(os.getcwd(), "setup_check_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--skip"]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 0
    n_coins = int(args[0]) if args else 60
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    try:
        tickers = m.get_tickers()
    except Exception as e:
        sys.exit(f"не удалось получить список монет с Gate: {e}")
    vols = {}
    for t in tickers:
        name = t.get("contract", "")
        if not name.endswith("_USDT") or name[:-5] in m.SNR_EXCLUDED_STABLES:
            continue
        try:
            vols[name] = float(t.get("volume_24h_quote") or t.get("volume_24h_settle") or 0)
        except (TypeError, ValueError):
            pass
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])][skip:skip + n_coins]
    disc, conf = syms[0::2], syms[1::2]
    if "--check" in sys.argv:
        return check_mode(m, syms, skip, sys.argv[sys.argv.index("--check") + 1])
    now = int(time.time())
    rng = random.Random(11)
    t0 = time.time()
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю: поиск {len(disc)}, подтверждение {len(conf)} · "
        f"{len(SETUPS)} сетапов x {len(TFS)} ТФ x {len(RRS)} тейка · стоп {STOP_ATR} ATR, до {MAX_HOLD} свечей")
    A = collect(m, disc, now, rng, "поиск")
    tests = []
    for key, rows in A.items():
        if len(rows) >= 40:
            s = stats(rows)
            tests.append((key, s, p_one_sided(s["t"])))
    # Benjamini-Hochberg over every test run
    tests.sort(key=lambda z: z[2])
    m_tests = len(tests)
    cut = 0
    for r_, (_, _, p) in enumerate(tests, 1):
        if p <= FDR_Q * r_ / m_tests:
            cut = r_
    chosen = [(k, s) for k, s, p in tests[:cut] if s["ex"] > 0 and s["h1"] > 0 and s["h2"] > 0]
    say(f"\n=== ПОИСК: {m_tests} проверок, лучшие 15 по t (превышение над случайным входом) ===")
    for (name, tf, rr), s, p in sorted(tests, key=lambda z: -(z[1]["t"] or -99))[:15]:
        say(fmt(name, tf, rr, s, len(disc)))
    say(f"\nпрошли отбор с поправкой на {m_tests} проверок (BH {int(FDR_Q * 100)}%) и в обеих половинах: {len(chosen)}")
    for (name, tf, rr), s in chosen:
        say(fmt(name, tf, rr, s, len(disc)))
    if not chosen:
        say("\nИТОГ: ни один сетап не отличается от случайного входа сильнее, чем бывает случайно при таком числе проверок")
    else:
        say(f"\n=== ПОДТВЕРЖДЕНИЕ на других {len(conf)} монетах ===")
        B = collect(m, conf, now, rng, "подтверждение")
        good = []
        for key, _ in chosen:
            rows = B.get(key) or []
            if len(rows) < 30:
                say(f"  {key[0]} {key[1]} RR{key[2]:g}: мало сделок ({len(rows)})")
                continue
            s = stats(rows)
            ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["raw"] > 0
            say(fmt(*key, s, len(conf)) + ("  ✓ ПОДТВЕРДИЛСЯ" if ok else ""))
            if ok:
                good.append(key)
        say(f"\nИТОГ: {'рабочие — ' + '; '.join(f'{k[0]} {k[1]} RR{k[2]:g}' for k in good) if good else 'на других монетах не подтвердился ни один'}")
        if good:
            say(f"ещё раз на совсем новых монетах: python setup_scan.py {n_coins} --skip {skip + n_coins}")
    say(f"время: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "setup_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: setup_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
