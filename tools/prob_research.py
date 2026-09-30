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
- Вход — открытие следующей свечи. Цель +TP% и стоп -SL% (для шорта наоборот),
  TP и SL — каждый из {0.3, 0.5, 0.75, 1, 1.5, 2, 3, 5}% (64 пары x 2 стороны);
  если за 72 свечи не случилось ни того, ни другого — «таймаут». Если в одной
  свече задеты оба — считается стоп (осторожно).
- Связка — условие на ВСЕХ монетах вместе (устойчиво, если работает на многих).
  Повторы одной связки на монете ближе 24 свечей не считаются (одна сделка).
- ВАЖНО: вероятность сравнивается с базой — той же целью/стопом у ЛЮБОЙ свечи
  без условия. При цели 1% и стопе 2% даже случайный вход доходит до цели
  примерно в 2/3 случаев; 90% что-то значит только на фоне этой базы.
- История каждой монеты делится по времени: поиск 60% / проверка 20% / тест 20%.
  Поиск: вероятность выше базы (поправка Бенджамини-Хохберга на число
  перебранных связок), плюс после комиссий. Проверка отбирает (выше базы с
  t >= 2 и плюс). Тест ничего не выбирает — только показывает, держится ли.
- Значимость на проверке и тесте считается ПО ДНЯМ: сделки разных монет в один
  день усредняются (монеты ходят вместе; календарное условие вроде «вторник»
  иначе выглядит в десятки раз надёжнее, чем есть).
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

TPS = (0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)
SLS = (0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)
LEVELS = tuple(sorted(set(TPS) | set(SLS)))
DIRS = ("LONG", "SHORT")
HOLD = 72
THIN = 24
FEE_PCT = 0.1
SPLIT = (0.6, 0.8)
MIN_N_MINE, MIN_N_VALID = 100, 30
FDR_Q = 0.05
VALID_Z = 2.0
TOP_KEYS_FOR_PAIRS = 15
MAX_TO_VALIDATE = 150
TEST_T = 1.65       # test: day-clustered t, one-sided 5%
PAIR_GAIN = 0.02    # a pair is kept only if its probability beats each own condition by >= 2 points
TARGETS = [(d, tp, sl) for d in DIRS for tp in TPS for sl in SLS]   # 128 bits

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
    # first bar where the price is >= level% above / below the entry; the levels
    # are sorted, so one pointer per side walks up as the running extreme grows
    up, dn = {}, {}
    ui = di = 0
    nl = len(LEVELS)
    for j in range(1, HOLD + 1):
        b = c[i + j]
        hi = (b["high"] / e - 1) * 100
        lo = (1 - b["low"] / e) * 100
        while ui < nl and hi >= LEVELS[ui]:
            up[LEVELS[ui]] = j
            ui += 1
        while di < nl and lo >= LEVELS[di]:
            dn[LEVELS[di]] = j
            di += 1
        if ui == nl and di == nl:
            break
    succ = fail = 0
    for k, (d, tp, sl) in enumerate(TARGETS):
        t_hit, s_hit = (up.get(tp), dn.get(sl)) if d == "LONG" else (dn.get(tp), up.get(sl))
        if t_hit is not None and (s_hit is None or t_hit < s_hit):
            succ |= 1 << k
        elif s_hit is not None:
            fail |= 1 << k
    return succ, fail


def tally(masks):
    """masks: list of (succ, fail[, day]) -> (n, [succ count per target], [fail count per target])"""
    n = len(masks)
    sc, fc = [0] * len(TARGETS), [0] * len(TARGETS)
    for (s, f), cnt in Counter(m_[:2] for m_ in masks).items():
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


def day_t(occ, k, p0):
    """Day-clustered t of (hit - p0) for target k: occurrences of one calendar
    day (all coins) are averaged first. Returns (t, number of days)."""
    days = {}
    for s, _f, d in occ:
        days.setdefault(d, []).append(((s >> k) & 1) - p0)
    xs = [sum(v) / len(v) for v in days.values()]
    nd = len(xs)
    if nd < 2:
        return None, nd
    mu = sum(xs) / nd
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (nd - 1))
    return (mu / (sd / math.sqrt(nd)) if sd > 0 else None), nd


def main():
    argv, args, skip, check = sys.argv[1:], [], 0, None
    i = 0
    while i < len(argv):
        if argv[i] == "--skip":
            skip, i = int(argv[i + 1]), i + 2
        elif argv[i] == "--best":   # --best "roc_zone=strong_down": every TP/SL for one situation
            check = ([tuple(x.split("=", 1)) for x in argv[i + 1].split(",")], None, None, None)
            i += 2
        elif argv[i] == "--check":   # --check "dow=1,dom_third=late" SHORT 0.5 0.5
            check = ([tuple(x.split("=", 1)) for x in argv[i + 1].split(",")], argv[i + 2].upper(),
                     float(argv[i + 3]), float(argv[i + 4]))
            i += 5
        else:
            args.append(argv[i])
            i += 1
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])][skip:skip + n_coins]
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
                bars.append((ci, i, part, fh[0], fh[1], conds[i], h1[i]["time"] // 86400))
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
        for ci, i, part, sm, fm, cd, day in bars:
            if not pred(cd):
                continue
            if i < last.get(ci, -10 ** 9) + THIN:
                continue
            last[ci] = i
            per[part].append((sm, fm, day))
        return per

    if check and check[1] is None:   # --best: which TP/SL makes the most of one situation
        conds_req = check[0]
        per = occurrences(lambda cd: all(str(cd.get(kk)) == vv for kk, vv in conds_req))
        allm = per[0] + per[1] + per[2]
        n, sc, fc = tally(allm)
        bn, bsc, _ = tally([(b[3], b[4]) for b in bars])
        say(f"\n=== ВСЕ ЦЕЛИ/СТОПЫ ДЛЯ СВЯЗКИ (монеты с {skip + 1}-й по {skip + len(syms)}-ю, весь период) ===")
        say("  " + " + ".join(f"{labels.get(kk, kk)} = {vv}" for kk, vv in conds_req) + f" · случаев {n}")
        if not n:
            say("  ни одного случая")
        else:
            rows = []
            for k, (d, tp, sl) in enumerate(TARGETS):
                p0 = bsc[k] / bn
                t, nd = day_t(allm, k, p0)
                rows.append((ev_pct(k, n, sc, fc), d, tp, sl, sc[k] / n, p0, t, 1 - (sc[k] + fc[k]) / n))
            # the auto-trader sizes by the risk at the stop, so the result that
            # matters is in R: % per trade / stop %
            ok = sorted((r for r in rows if (r[6] or 0) >= 2), key=lambda r: -(r[0] / r[3]))
            say("  лучшие по R на сделку (результат / стоп; среди выше базы с t по дням >= 2):")
            for ev, d, tp, sl, p, p0, t, to in ok[:12]:
                say(f"    {d} +{tp}% раньше −{sl}%: {p * 100:.0f}% (база {p0 * 100:.0f}%) · t={t:.1f} · "
                    f"{ev / sl:+.2f}R ({ev:+.2f}%) на сделку · таймаут {to * 100:.0f}%")
            if ok:
                ev, d, tp, sl = ok[0][:4]
                say(f"\n  ВЫБОР (правило: максимум R на сделку): {d} +{tp}% раньше −{sl}%")
                say(f"  проверка на других монетах: --check \"{','.join(f'{kk}={vv}' for kk, vv in conds_req)}\" {d} {tp} {sl}")
            else:
                say("  ни один вариант не выше базы с t >= 2")
        say(f"\nвремя: {time.time() - t0:.0f} с")
        with open(os.path.join(os.getcwd(), "prob_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        return

    if check:   # one fixed situation, nothing searched: the whole period is a clean test
        conds_req, d, tp, sl = check
        k = TARGETS.index((d, tp, sl))
        per = occurrences(lambda cd: all(str(cd.get(kk)) == vv for kk, vv in conds_req))
        say(f"\n=== ПРОВЕРКА ОДНОЙ СВЯЗКИ (монеты с {skip + 1}-й по {skip + len(syms)}-ю) ===")
        say(f"  {d} +{tp}% раньше −{sl}%  ·  " + " + ".join(f"{labels.get(kk, kk)} = {vv}" for kk, vv in conds_req))
        allm = per[0] + per[1] + per[2]
        n, sc, fc = tally(allm)
        bn, bsc, _ = tally([(b[3], b[4]) for b in bars])
        if not n:
            say("  ни одного случая")
        else:
            p, p0 = sc[k] / n, bsc[k] / bn
            z, nd = day_t(allm, k, p0)
            ev = ev_pct(k, n, sc, fc)
            say(f"  весь период: {p * 100:.0f}% (база {p0 * 100:.0f}%) · t по дням={z if z is None else round(z, 2)} "
                f"({nd} дн.) · {ev:+.2f}%/сделку · n={n}")
            for part, lbl in ((0, "первые 60%"), (1, "следующие 20%"), (2, "последние 20%")):
                pn, psc, pfc = tally(per[part])
                bpn, bpsc, _ = base[part]
                if pn:
                    say(f"    {lbl}: {psc[k] / pn * 100:.0f}% (база {bpsc[k] / bpn * 100:.0f}%) · "
                        f"{ev_pct(k, pn, psc, pfc):+.2f}%/сделку · n={pn}")
            ok = (z or 0) >= 2 and ev > 0
            say(f"  ВЕРДИКТ: {'подтвердилась на других монетах' if ok else 'не подтвердилась'} "
                f"(нужно: выше базы с t по дням >= 2 и плюс после комиссий)")
        say(f"\nвремя: {time.time() - t0:.0f} с")
        with open(os.path.join(os.getcwd(), "prob_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        return

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
        t, nd = day_t(c["per"][part], k, p0)   # clustered by calendar day
        return {"n": n, "p": p, "p0": p0, "z": t, "days": nd, "ev": ev_pct(k, n, sc, fc),
                "to": 1 - (sc[k] + fc[k]) / n}

    to_validate, per_cond = [], Counter()
    for c in passed:   # best by mining z, at most 3 targets per situation (variety)
        if per_cond[c["cond"]] < 3:
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
        tz = f" · t(дни)={s['z']:.1f} ({s['days']} дн.)" if s.get("days") and s.get("z") is not None else ""
        return f"{s['p'] * 100:.0f}% (база {s['p0'] * 100:.0f}%) · {s['ev']:+.2f}%/сделку · n={s['n']}{tz}{to}"

    def held_ok(te):
        return te.get("n", 0) >= 20 and (te.get("z") or 0) >= TEST_T and (te.get("ev") or 0) > 0

    say(f"\n=== ПРОШЛИ ПРОВЕРКУ: {len(confirmed)} (из {len(to_validate)} лучших по поиску) ===")
    if not confirmed:
        say("  ни одна связка не удержала вероятность выше базы на проверке — устойчивых связок нет")
    shown = sorted(confirmed, key=lambda c: (not held_ok(c["test"]), -c["valid"]["p"]))[:20]
    held = sum(1 for c in confirmed if held_ok(c["test"]))
    for c in shown:
        d, tp, sl = TARGETS[c["k"]]
        te = c["test"]
        say(f"\n  {'✓' if held_ok(te) else '✗'} {d} +{tp}% раньше −{sl}%  ·  {cond_txt(c['cond'])}")
        say(f"     поиск:    {st({'n': c['n'], 'p': c['p'], 'p0': c['p0'], 'ev': c['ev']})}")
        say(f"     проверка: {st(c['valid'])}")
        say(f"     ТЕСТ:     {st(te)}")
    if confirmed:
        say(f"\n  на тесте удержались: {held} из {len(confirmed)}")
    say(f"  ✓ = на тесте (его не видел ни поиск, ни проверка): выше базы с t по дням >= {TEST_T} и плюс после комиссий")
    say(f"\nвремя: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "prob_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: prob_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
