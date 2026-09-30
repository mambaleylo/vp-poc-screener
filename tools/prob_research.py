#!/usr/bin/env python3
"""Связки условий Neuro, после которых цена с высокой вероятностью проходит
X% в нужную сторону раньше, чем Y% против. Проверка на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python prob_research.py [число монет, по умолчанию 20] [дней, по умолчанию 365]

Ничего не торгует и не пишет в состояние сервера. Отчёт печатается и
сохраняется в prob_report.txt.

Как устроено (всё задано заранее, ничего не подбирается под результат):
- 1ч свечи, условия — те же, что считает Neuro на каждой свече (RSI, тренды
  4ч/1д, фандинг, BTC/ETH, серии, объём, сессия, закрытие дня и т.д.) и их пары.
- Вход — открытие следующей свечи. Цель +TP% и стоп -SL% (для шорта наоборот):
  TP из {0.5, 1, 1.5, 2}%, SL из {0.5, 1, 2, 3}%; если за 48 свечей не
  случилось ни того, ни другого — «таймаут». Если в одной свече задеты оба —
  считается стоп (осторожно).
- Связка — условие на ВСЕХ монетах вместе (устойчиво, если работает на многих).
  Повторы одной связки на монете ближе 24 свечей не считаются (одна сделка).
- ВАЖНО: вероятность сравнивается с базой — той же целью/стопом у ЛЮБОЙ свечи
  без условия. При цели 1% и стопе 2% даже случайный вход доходит до цели
  примерно в 2/3 случаев; 90% что-то значит только на фоне этой базы.
- История каждой монеты делится по времени: поиск 60% / проверка 20% / тест 20%.
  Поиск: вероятность выше базы (поправка Бенджамини-Хохберга на число
  перебранных связок), плюс после комиссий. Проверка отбирает (выше базы с
  z >= 2 и плюс). Тест ничего не выбирает — только показывает, держится ли.
- «% на сделку» = вероятность x TP - доля стопов x SL - комиссии 0.1%
  (таймаут считается нулём).
"""
import importlib.util
import math
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")

TPS = (0.5, 1.0, 1.5, 2.0)
SLS = (0.5, 1.0, 2.0, 3.0)
DIRS = ("LONG", "SHORT")
HOLD = 48
THIN = 24
FEE_PCT = 0.1
SPLIT = (0.6, 0.8)
MIN_N_MINE, MIN_N_VALID = 100, 30
FDR_Q = 0.05
VALID_Z = 2.0
TOP_KEYS_FOR_PAIRS = 15
MAX_TO_VALIDATE = 60
PAIR_GAIN = 0.02    # a pair is kept only if its probability beats each own condition by >= 2 points
TARGETS = [(d, tp, sl) for d in DIRS for tp in TPS for sl in SLS]   # 32 bits

OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def first_hits(c, i):
    """Bars (1..HOLD) until each TP / SL level is first touched after entering at
    c[i+1].open, for LONG and SHORT. None = not within HOLD bars. Returns
    (succ_mask, fail_mask) over TARGETS, or None if there is no full window."""
    if i + HOLD >= len(c):
        return None
    e = c[i + 1]["open"]
    if not e or e <= 0:
        return None
    up = {tp: None for tp in TPS}
    dn = {sl: None for sl in SLS}      # long: price down by sl; short: price down by tp
    up_sl = {sl: None for sl in SLS}   # short stop: price up by sl
    dn_tp = {tp: None for tp in TPS}   # short target: price down by tp
    for j in range(1, HOLD + 1):
        b = c[i + j]
        hi = (b["high"] / e - 1) * 100
        lo = (1 - b["low"] / e) * 100
        for tp in TPS:
            if up[tp] is None and hi >= tp:
                up[tp] = j
            if dn_tp[tp] is None and lo >= tp:
                dn_tp[tp] = j
        for sl in SLS:
            if dn[sl] is None and lo >= sl:
                dn[sl] = j
            if up_sl[sl] is None and hi >= sl:
                up_sl[sl] = j
    succ = fail = 0
    for k, (d, tp, sl) in enumerate(TARGETS):
        t_hit, s_hit = (up[tp], dn[sl]) if d == "LONG" else (dn_tp[tp], up_sl[sl])
        if t_hit is not None and (s_hit is None or t_hit < s_hit):
            succ |= 1 << k
        elif s_hit is not None:
            fail |= 1 << k
    return succ, fail


def tally(masks):
    """masks: list of (succ, fail) -> (n, [succ count per target], [fail count per target])"""
    n = len(masks)
    sc, fc = [0] * len(TARGETS), [0] * len(TARGETS)
    for (s, f), cnt in Counter(masks).items():
        k = 0
        while s >> k:
            if (s >> k) & 1:
                sc[k] += cnt
            k += 1
        k = 0
        while f >> k:
            if (f >> k) & 1:
                fc[k] += cnt
            k += 1
    return n, sc, fc


def ev_pct(k, n, sc, fc):
    _, tp, sl = TARGETS[k]
    return (sc[k] * tp - fc[k] * sl) / n - FEE_PCT if n else None


def z_vs(p, p0, n):
    return (p - p0) / math.sqrt(p0 * (1 - p0) / n) if n and 0 < p0 < 1 else None


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n_coins = int(args[0]) if args else 20
    days = int(args[1]) if len(args) > 1 else 365
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    labels = getattr(m, "NEURO_COND_LABELS", {})
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])[:n_coins]]
    now = int(time.time())
    start = now - days * 86400
    warm = start - 60 * 86400   # indicator warm-up (EMA200 etc.) before the studied period
    t0 = time.time()
    say(f"монет: {len(syms)} · {days} дн. 1ч · цели {TPS}% · стопы {SLS}% · до {HOLD} свечей · комиссия {FEE_PCT}%")
    btc = m.get_candles_range("BTC_USDT", "1h", warm, now) or []
    eth = m.get_candles_range("ETH_USDT", "1h", warm, now) or []

    # per bar: (coin, i, part, succ, fail, conds)
    bars = []
    for ci, s in enumerate(syms):
        try:
            h1 = [c for c in (m.get_candles_range(s, "1h", warm, now) or []) if c["time"] + 3600 <= now]
            if len(h1) < 24 * 120:
                print(f"  {s}: мало истории, пропуск")
                continue
            h4 = m.get_candles_range(s, "4h", warm - 30 * 86400, now) or []
            d1 = m.get_candles_range(s, "1d", warm - 120 * 86400, now) or []
            fr = m.neuro_fetch_funding_rate(s, warm, now)
            try:
                m.neuro_set_index_context(s, warm, now)
            except Exception:
                pass
            try:
                oi = m.get_contract_stats(s, interval="1h", limit=999)
            except Exception:
                oi = []
            conds = m.neuro_compute_conditions(h1, h4, fr, None if s == "BTC_USDT" else btc, d1, oi,
                                               None if s == "ETH_USDT" else eth)
            idx0 = next((k for k, c in enumerate(h1) if c["time"] >= start), None)
            if idx0 is None:
                continue
            n_st = len(h1) - idx0
            b1, b2 = idx0 + int(n_st * SPLIT[0]), idx0 + int(n_st * SPLIT[1])
            for i in range(idx0, len(h1) - HOLD - 1):
                fh = first_hits(h1, i)
                if fh is None:
                    continue
                part = 0 if i < b1 else (1 if i < b2 else 2)
                bars.append((ci, i, part, fh[0], fh[1], conds[i]))
        except Exception as e:
            print(f"  {s}: {e}")
        print(f"  ...{ci + 1}/{len(syms)} ({time.time() - t0:.0f} с)")
    if not bars:
        sys.exit("нет данных")
    say(f"свечей с условиями: {len(bars)}")

    base = {p: tally([(b[3], b[4]) for b in bars if b[2] == p]) for p in (0, 1, 2)}

    def occurrences(pred):
        """(succ, fail) per part for bars where pred(conds) holds, thinned per coin"""
        per = {0: [], 1: [], 2: []}
        last = {}
        for ci, i, part, sm, fm, cd in bars:
            if not pred(cd):
                continue
            if i < last.get(ci, -10 ** 9) + THIN:
                continue
            last[ci] = i
            per[part].append((sm, fm))
        return per

    # --- mining: single conditions
    keys = [k for k in m.NEURO_CONDITION_KEYS if k not in ("hour", "streak", "daily_streak")]
    single_vals = {}
    for b in bars:
        for k in keys:
            v = b[5].get(k)
            if v is not None:
                single_vals.setdefault(k, set()).add(v)
    cands = []   # (key tuple, per-part tallies)
    key_best = {}
    single_p = {}   # ((key, value), target) -> mining probability
    tested = 0

    def mine(ctuple, per):
        nonlocal tested
        n, sc, fc = tally(per[0])
        if n < MIN_N_MINE:
            return
        bn, bsc, bfc = base[0]
        for k in range(len(TARGETS)):
            p, p0 = sc[k] / n, bsc[k] / bn
            if len(ctuple) == 1:
                single_p[(ctuple[0], k)] = p
            z = z_vs(p, p0, n)
            tested += 1
            if z is None or z <= 0:
                continue
            # a pair must add something to each of its own conditions (else it is
            # just the stronger single condition with a passenger)
            if len(ctuple) == 2 and p < max(single_p.get((ctuple[0], k), 0), single_p.get((ctuple[1], k), 0)) + PAIR_GAIN:
                continue
            ev = ev_pct(k, n, sc, fc)
            cands.append({"cond": ctuple, "k": k, "z": z, "pval": norm_sf(z), "p": p, "p0": p0, "n": n, "ev": ev,
                          "per": per})
            for kk, _ in ctuple:
                key_best[kk] = max(key_best.get(kk, 0), z)

    for k in keys:
        for v in single_vals.get(k, ()):
            mine(((k, v),), occurrences(lambda cd, k=k, v=v: cd.get(k) == v))
    print(f"  одиночные условия готовы ({time.time() - t0:.0f} с)")
    top_keys = [k for k, _ in sorted(key_best.items(), key=lambda kv: -kv[1])[:TOP_KEYS_FOR_PAIRS]]
    for a in range(len(top_keys)):
        for b in range(a + 1, len(top_keys)):
            k1, k2 = top_keys[a], top_keys[b]
            for v1 in single_vals.get(k1, ()):
                for v2 in single_vals.get(k2, ()):
                    mine(((k1, v1), (k2, v2)),
                         occurrences(lambda cd, k1=k1, v1=v1, k2=k2, v2=v2: cd.get(k1) == v1 and cd.get(k2) == v2))
    print(f"  пары условий готовы ({time.time() - t0:.0f} с)")

    # Benjamini-Hochberg over everything tested, then must make money on the mining part
    cands.sort(key=lambda c: c["pval"])
    passed = []
    for r, c in enumerate(cands, 1):
        if c["pval"] <= FDR_Q * r / max(1, tested):
            passed = cands[:r]
    passed = [c for c in passed if c["ev"] is not None and c["ev"] > 0]
    passed.sort(key=lambda c: -c["z"])
    say(f"перебрано вариантов (связка x цель/стоп x сторона): {tested} · прошли поиск: {len(passed)}")

    # --- validation (chooses) and test (only reports)
    def part_stats(c, part):
        n, sc, fc = tally(c["per"][part])
        bn, bsc, _ = base[part]
        if not n:
            return {"n": 0}
        k = c["k"]
        p, p0 = sc[k] / n, bsc[k] / bn
        return {"n": n, "p": p, "p0": p0, "z": z_vs(p, p0, n), "ev": ev_pct(k, n, sc, fc),
                "to": 1 - (sc[k] + fc[k]) / n}

    to_validate, per_cond = [], Counter()
    for c in passed:   # best by mining z, at most 4 targets per situation (variety)
        if per_cond[c["cond"]] < 4:
            per_cond[c["cond"]] += 1
            to_validate.append(c)
        if len(to_validate) >= MAX_TO_VALIDATE:
            break
    confirmed = []
    for c in to_validate:
        v = part_stats(c, 1)
        if v["n"] >= MIN_N_VALID and (v["z"] or 0) >= VALID_Z and (v["ev"] or 0) > 0:
            c["valid"], c["test"] = v, part_stats(c, 2)
            confirmed.append(c)
    # one line per situation: its best target by the validation probability
    best_per_cond = {}
    for c in confirmed:
        b = best_per_cond.get(c["cond"])
        if b is None or c["valid"]["p"] > b["valid"]["p"]:
            best_per_cond[c["cond"]] = c
    confirmed = sorted(best_per_cond.values(), key=lambda c: -c["valid"]["p"])

    def cond_txt(ct):
        return " + ".join(f"{labels.get(k, k)} = {v}" for k, v in ct)

    def st(s):
        if not s.get("n"):
            return "нет сделок"
        to = f" · таймаут {s['to'] * 100:.0f}%" if s.get("to") else ""
        return f"{s['p'] * 100:.0f}% (база {s['p0'] * 100:.0f}%) · {s['ev']:+.2f}%/сделку · n={s['n']}{to}"

    say(f"\n=== ПРОШЛИ ПРОВЕРКУ: {len(confirmed)} (из {min(len(passed), MAX_TO_VALIDATE)} лучших по поиску) ===")
    if not confirmed:
        say("  ни одна связка не удержала вероятность выше базы на проверке — устойчивых связок нет")
    held = 0
    for c in confirmed[:15]:
        d, tp, sl = TARGETS[c["k"]]
        te = c["test"]
        ok = te.get("n", 0) >= 20 and (te.get("p") or 0) > (te.get("p0") or 1) and (te.get("ev") or 0) > 0
        held += ok
        say(f"\n  {'✓' if ok else '✗'} {d} +{tp}% раньше −{sl}%  ·  {cond_txt(c['cond'])}")
        say(f"     поиск:    {st({'n': c['n'], 'p': c['p'], 'p0': c['p0'], 'ev': c['ev']})}")
        say(f"     проверка: {st(c['valid'])}")
        say(f"     ТЕСТ:     {st(te)}")
    if confirmed:
        say(f"\n  на тесте удержались (выше базы и в плюсе): {held} из {min(15, len(confirmed))}")
    say("  ✓ = на тесте (его не видел ни поиск, ни проверка) вероятность выше базы и плюс после комиссий")
    say(f"\nвремя: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "prob_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: prob_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
