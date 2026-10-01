#!/usr/bin/env python3
"""Ликвидации и открытый интерес (OI) — есть ли после них направление цены. РЕАЛЬНЫЕ данные Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python liq_research.py [число монет, по умолчанию 40]
    python liq_research.py 60 --skip 40     # проверка на ДРУГИХ монетах (с 41-й по 100-ю)

Ничего не торгует. Часовая статистика контрактов (/futures/usdt/contract_stats:
ликвидации лонгов/шортов в $, OI) + часовые свечи. История кэшируется в liq_cache/.

Гипотезы заданы ЗАРАНЕЕ (пороги считаются по прошлым 30 дням САМОЙ монеты,
пересчёт раз в сутки — без заглядывания вперёд):
 1. КАСКАД ЛИКВИДАЦИЙ ЛОНГОВ → ЛОНГ (отскок): ликвидации лонгов за час выше
    99-го перцентиля и выше 3 средних.
 2. КАСКАД ЛИКВИДАЦИЙ ШОРТОВ → ШОРТ (откат после сквиза): то же для шортов.
 3. ТОЛПА В ЛОНГАХ → ШОРТ: за 24ч цена выросла сильнее 90% случаев И OI вырос
    сильнее 90% случаев. Зеркально, толпа в шортах (цена вниз, OI вверх) → ЛОНГ.
 4. ВЫНОС ПЛЕЧА → ЛОНГ: за 24ч цена упала сильнее 90% случаев И OI упал
    сильнее 90% случаев (позиции закрыты, давление продаж кончилось).
Вход по открытию следующего часа, выход через 4ч / 12ч / 24ч. Сигнал на монете
не чаще раза в 24ч. Комиссия 0.1% за круг.

Сравнение — с обычным часом той же монеты (её средний ход за тот же срок):
превышение = сделка минус средний ход монеты в ту же сторону. Гипотеза проходит,
если превышение > 0, t по ДНЯМ >= 2.5 (поправка на 12 проверок), превышение в
обеих половинах периода и сама сделка в плюсе после комиссии. Прошедшее надо
потом подтвердить на других монетах (--skip).
"""
import importlib.util
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")

H = 3600
DAYS = 400
HOLDS = (4, 12, 24)
FEE = 0.001
PASS_T = 2.5
WIN = 30 * 24          # hours of own history for thresholds
MIN_PAST = 10 * 24
COOLDOWN = 24
CACHE = os.path.join(os.getcwd(), "liq_cache")
OUT, DIAG = [], []


def say(s=""):
    print(s)
    OUT.append(s)


def tstat(xs):
    n = len(xs)
    if n < 3:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def pct(sorted_xs, q):
    if not sorted_xs:
        return None
    return sorted_xs[min(len(sorted_xs) - 1, int(q * len(sorted_xs)))]


def _get(m, params):
    r = m.requests.get(f"{m.GATE_BASE}/futures/usdt/contract_stats", params=params, timeout=m.HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {r.text[:100]}")
    return r.json()


def _row(c):
    try:
        t = int(c.get("time", 0))
        f = lambda k: float(c[k]) if c.get(k) is not None else 0.0
        return t, {"oi": f("open_interest"), "ll": f("long_liq_usd"), "sl": f("short_liq_usd")}
    except (TypeError, ValueError):
        return None


def stats_history(m, sym, start, now):
    """Hourly contract stats from `start`, paging forward with from+limit.
    Gate's depth for this endpoint is unknown, so try progressively shorter
    look-backs until one returns data; every refusal goes to DIAG."""
    path = os.path.join(CACHE, f"{sym}.json")
    rows = {}
    try:
        with open(path) as f:
            rows = {int(k): v for k, v in json.load(f).items()}
    except Exception:
        pass
    t = max(rows) + H if rows else None
    if t is None:
        for back_days in (DAYS, 180, 90, 30, 7):
            s = max(start, now - back_days * 86400)
            try:
                data = _get(m, {"contract": sym, "interval": "1h", "from": s, "limit": 100})
            except Exception as e:
                DIAG.append(f"{sym} from {back_days}д: {e}")
                continue
            if data:
                t = s
                break
        if t is None:
            try:   # last resort: the form the main script uses (no from)
                for c in _get(m, {"contract": sym, "interval": "1h", "limit": 100}):
                    x = _row(c)
                    if x:
                        rows[x[0]] = x[1]
            except Exception as e:
                DIAG.append(f"{sym} без from: {e}")
            return rows
    for _ in range(400):
        if t > now - H:
            break
        try:
            data = _get(m, {"contract": sym, "interval": "1h", "from": t, "limit": 100})
        except Exception as e:
            DIAG.append(f"{sym} страница: {e}")
            break
        if not data:
            break
        last = t
        for c in data:
            x = _row(c)
            if x:
                rows[x[0]] = x[1]
                last = max(last, x[0])
        if last < t:
            break
        t = last + H
    try:
        os.makedirs(CACHE, exist_ok=True)
        with open(path, "w") as f:
            json.dump({str(k): v for k, v in rows.items()}, f)
    except Exception:
        pass
    return rows


HYPS = [("1. каскад ликвидаций ЛОНГОВ → лонг", "ll"),
        ("2. каскад ликвидаций ШОРТОВ → шорт", "sl"),
        ("3. толпа: цена и OI вместе → против", "crowd"),
        ("4. вынос плеча: цена и OI вниз → лонг", "flush")]


def study(cs, st):
    """-> {hyp: {hold: [(t, raw net return, excess)]}}"""
    times = [c["time"] for c in cs]
    n = len(cs)
    closes = [c["close"] for c in cs]
    # coin's own mean move per horizon (the "ordinary hour" baseline)
    drift = {}
    for hd in HOLDS:
        xs = [cs[i + hd]["close"] / cs[i + 1]["open"] - 1 for i in range(n - hd - 1)]
        drift[hd] = sum(xs) / len(xs) if xs else 0.0
    ll = [st.get(t, {}).get("ll") for t in times]
    sl = [st.get(t, {}).get("sl") for t in times]
    oi = [st.get(t, {}).get("oi") for t in times]
    dp = [None] * n
    doi = [None] * n
    for i in range(24, n):
        dp[i] = closes[i] / closes[i - 24] - 1
        if oi[i] and oi[i - 24]:
            doi[i] = oi[i] / oi[i - 24] - 1
    res = {h[1]: {hd: [] for hd in HOLDS} for h in HYPS}
    last_sig = {h[1]: -10 ** 9 for h in HYPS}
    thr, thr_day = {}, None
    for i in range(MIN_PAST, n - max(HOLDS) - 1):
        day = times[i] // 86400
        if day != thr_day:
            lo = max(0, i - WIN)
            thr_day = day
            for k, arr in (("ll", ll), ("sl", sl)):
                w = sorted(x for x in arr[lo:i] if x is not None)
                thr[k] = None if len(w) < MIN_PAST else max(pct(w, 0.99), 3 * sum(w) / len(w), 1.0)
            wp = sorted(x for x in dp[lo:i] if x is not None)
            wo = sorted(x for x in doi[lo:i] if x is not None)
            ok = len(wp) >= MIN_PAST and len(wo) >= MIN_PAST
            thr["p_hi"], thr["p_lo"] = (pct(wp, 0.9), pct(wp, 0.1)) if ok else (None, None)
            thr["o_hi"], thr["o_lo"] = (pct(wo, 0.9), pct(wo, 0.1)) if ok else (None, None)
        sigs = []
        if thr.get("ll") and ll[i] is not None and ll[i] > thr["ll"]:
            sigs.append(("ll", 1))
        if thr.get("sl") and sl[i] is not None and sl[i] > thr["sl"]:
            sigs.append(("sl", -1))
        if thr.get("p_hi") is not None and dp[i] is not None and doi[i] is not None:
            if doi[i] > thr["o_hi"] and dp[i] > thr["p_hi"]:
                sigs.append(("crowd", -1))
            elif doi[i] > thr["o_hi"] and dp[i] < thr["p_lo"]:
                sigs.append(("crowd", 1))
            if doi[i] < thr["o_lo"] and dp[i] < thr["p_lo"]:
                sigs.append(("flush", 1))
        for k, side in sigs:
            if i - last_sig[k] < COOLDOWN:
                continue
            last_sig[k] = i
            e = cs[i + 1]["open"]
            for hd in HOLDS:
                mv = cs[i + hd]["close"] / e - 1
                res[k][hd].append((times[i], side * mv - FEE, side * (mv - drift[hd])))
    return res


def judge(rows):
    if len(rows) < 30:
        return None
    rows = sorted(rows)
    days = {}
    for t, raw, ex in rows:
        days.setdefault(t // 86400, []).append(ex)
    td = tstat([sum(v) / len(v) for v in days.values()])
    half = len(rows) // 2
    h = lambda p: sum(x[2] for x in p) / len(p)
    raw = sum(x[1] for x in rows) / len(rows)
    ex = sum(x[2] for x in rows) / len(rows)
    ok = ex > 0 and (td or 0) >= PASS_T and h(rows[:half]) > 0 and h(rows[half:]) > 0 and raw > 0
    return {"n": len(rows), "days": len(days), "raw": raw, "ex": ex, "t": td,
            "h1": h(rows[:half]), "h2": h(rows[half:]),
            "wr": sum(1 for x in rows if x[1] > 0) / len(rows) * 100, "ok": ok}


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--skip"]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 0
    n_coins = int(args[0]) if args else 40
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
    now = int(time.time())
    start = now - DAYS * 86400
    t0 = time.time()
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю · часовые данные · выход через {HOLDS} ч")
    allres = {h[1]: {hd: [] for hd in HOLDS} for h in HYPS}
    depth = []
    for k, s in enumerate(syms, 1):
        try:
            cs = m.get_candles_range(s, "1h", start, now) or []
            cs = [c for c in cs if c["time"] + H <= now]
        except Exception as e:
            print(f"  {s} свечи: {e}")
            continue
        st = stats_history(m, s, start, now)
        if k == 1 and st:
            say(f"пример статистики {s}: {len(st)} часов с {time.strftime('%Y-%m-%d', time.gmtime(min(st)))}")
        if len(cs) < 500 or len(st) < MIN_PAST + 100:
            print(f"  {s}: мало данных (свечей {len(cs)}, статистики {len(st)})")
            continue
        depth.append(len(st) / 24)
        r = study(cs, st)
        for key in r:
            for hd in HOLDS:
                allres[key][hd] += r[key][hd]
        if k % 5 == 0:
            print(f"  ...{k}/{len(syms)} ({time.time() - t0:.0f} с)")
    if DIAG:
        say(f"\nотказы API ({len(DIAG)}), первые: " + " | ".join(DIAG[:3]))
    if not depth:
        sys.exit("нет статистики контрактов — см. отказы выше")
    say(f"монет с данными: {len(depth)} · история статистики в среднем {sum(depth) / len(depth):.0f} дн.")
    passed = []
    for title, key in HYPS:
        say(f"\n=== {title} ===")
        for hd in HOLDS:
            j = judge(allres[key][hd])
            if j is None:
                say(f"  {hd:2d}ч: мало сигналов ({len(allres[key][hd])})")
                continue
            per_day = j["n"] / max(sum(depth) / len(depth), 1)
            td = "—" if j["t"] is None else f"{j['t']:.2f}"
            say(f"  {hd:2d}ч: сигналов {j['n']} (≈{per_day:.1f} в день) · WR {j['wr']:.0f}% · сделка {j['raw'] * 100:+.2f}% · "
                f"превышение {j['ex'] * 100:+.2f}% · t(дни)={td} · половины {j['h1'] * 100:+.2f}% / {j['h2'] * 100:+.2f}%"
                f"{'  ✓ ПРОШЛА' if j['ok'] else ''}")
            if j["ok"]:
                passed.append(f"{title} / {hd}ч")
    say(f"\nИТОГ: прошли — {'; '.join(passed) if passed else 'ни одна'}")
    if passed:
        say(f"подтвердить на других монетах: python liq_research.py 60 --skip {skip + n_coins}")
    say(f"время: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "liq_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: liq_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
