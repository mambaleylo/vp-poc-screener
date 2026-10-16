"""EMA research — causal indicator series, the same formulas the bot will use (pure Python, lists)."""
import math
TFS = ("4h", "1d", "1w", "1M")
EMAS = {"4h": (20, 50, 100, 200), "1d": (7, 14, 21, 28, 50, 100, 200), "1w": (7, 14, 21, 28, 50, 100, 200),
        "1M": (7, 14, 21, 28, 50, 100, 200)}
TF_I = {"4h": 0, "1d": 1, "1w": 2, "1M": 3}

def ema_series(closes, n):
    """SMA-seeded EMA (as the bot's emw_ema); None before n values"""
    out = [None] * len(closes)
    if len(closes) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(closes[:n]) / n
    out[n - 1] = e
    for i in range(n, len(closes)):
        e = closes[i] * k + e * (1 - k)
        out[i] = e
    return out

def atr_series(bars, n=14):
    """simple mean of the last n true ranges (None before n)"""
    tr = [bars[0]["high"] - bars[0]["low"]] + [max(bars[i]["high"] - bars[i]["low"], abs(bars[i]["high"] - bars[i - 1]["close"]),
                                                   abs(bars[i]["low"] - bars[i - 1]["close"])) for i in range(1, len(bars))]
    out = [None] * len(bars)
    s = 0.0
    for i, v in enumerate(tr):
        s += v
        if i >= n:
            s -= tr[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out

def rsi_series(closes, n=14):
    """Wilder's RSI; None before n+1 values"""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0.0)
        l += max(-d, 0.0)
    g /= n
    l /= n
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (n - 1) + max(d, 0.0)) / n
        l = (l * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out
