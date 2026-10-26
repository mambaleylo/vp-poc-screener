"""the bot's view of a classic event, in numpy: the windows the live bot has (1h: the last W1 bars, 4h: the last W4 bars,
1d: the last WD bars — Binance's own klines, here aggregated from the research's 1h bars), the ev3 indicators on the 4h /
1d windows and the ev2 features on the 1h window -> compared with the research's full-history ev3/<SYM>.npz"""
import sys, json, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
import lv_engine as LE, ev2_engine as E2, ev3_engine as E3
from lv_engine import agg, wilder_atr, rsi, ema
W1, W4, WD = 3000, 1500, 1000
def tf_bars(T, O, H, L, C, sec, t_end, w):
    pid = T // sec; g = agg(pid, O, H, L, C); st, en = g[5], g[6]
    full = (en - st) == sec // 3600; bt = g[0] * sec
    k = np.searchsorted(bt, t_end)            # TF bars that started before t_end
    keep = np.arange(len(bt))[:k][-w:]
    return bt[keep], g[1][keep], g[2][keep], g[3][keep], g[4][keep], full[keep]
def events_at(sym, tsig, fam_want=None):
    """the events whose 1h signal bar is at tsig (its open time), with the bot's windows"""
    T, O, H, L, C, V = LE.load_np(sym)
    out = []
    for tfi, sec in ((0, 14400), (1, 86400)):
        if (tsig + 3600) % sec: continue
        bt, bo, bh, bl, bc, full = tf_bars(T, O, H, L, C, sec, tsig + 3600, W4 if tfi == 0 else WD)
        if not len(bt) or bt[-1] + sec != tsig + 3600: continue
        for i, k, s in E3.tf_events(bo, bh, bl, bc):
            if i == len(bt) - 1 and full[i]: out.append((2 * k + tfi, s))
    return out
_BW = {}
def feats(sym, tsig, fam, side):
    T, O, H, L, C, V = LE.load_np(sym)
    J = int(np.searchsorted(T, tsig)); a0 = max(0, J - W1 + 1)
    T1, O1, H1, L1, C1, V1 = (x[a0:J + 1] for x in (T, O, H, L, C, V)); j = len(T1) - 1
    bt, bo, bh, bl, bc, _ = tf_bars(T, O, H, L, C, 86400, tsig + 3600, WD + 1)   # the days up to the signal's own (forming) one
    dpi_j = len(bt) - 1 if bt[-1] == (tsig // 86400) * 86400 else len(bt)          # the signal hour's day index in that list
    dC = bc; datr_d = wilder_atr(bh, bl, dC) / dC * 100
    dat = datr_d[dpi_j - 1]
    BT, BO, BH, BL, BC, BV = LE.load_np("BTCUSDT")
    bj_full = np.clip(np.searchsorted(BT, T1, side="right") - 1, 0, len(BT) - 1); bC = BC[bj_full]
    # BTC daily (the window) for b_e50
    bbt, _, _, _, bbc, _ = tf_bars(BT, BO, BH, BL, BC, 86400, tsig + 3600, WD + 1)
    be50 = ema(bbc, 50); bday = (BT[bj_full[j]] // 86400) * 86400; bdi = max(int(np.searchsorted(bbt, bday)) - 1, 0)
    M = E2.metrics(sym, T1)
    S = side; px = C1[j]; dpx = dat / 100 * px
    f = np.zeros(31)
    f[0] = fam; f[1] = S; f[2] = dat; f[3] = (T1[j] // 3600) % 24; f[4] = ((T1[j] // 86400) + 3) % 7
    ret = lambda k: (C1[j] / C1[max(j - k, 0)] - 1) * 100
    f[5] = S * ret(4); f[6] = S * ret(24); f[7] = S * ret(72); f[8] = S * ret(168)
    f[9] = S * (bC[j] / bC[max(j - 24, 0)] - 1) * 100; f[10] = S * (bC[j] / bC[max(j - 168, 0)] - 1) * 100
    be = be50[bdi]; f[11] = S * (bbc[bdi] / be - 1) * 100 if np.isfinite(be) else 0
    rd = rsi(dC)[dpi_j - 1]; f[12] = S * ((rd if np.isfinite(rd) else 50) - 50); f[13] = S * (rsi(C1)[j] - 50)
    e50 = ema(dC, 50)[dpi_j - 1]; e200 = ema(dC, 200)[dpi_j - 1]
    f[14] = np.nan_to_num(S * (px - e50) / dpx); f[15] = np.nan_to_num(S * (px - e200) / dpx)
    kd = dpi_j - 1
    for c_, w in ((16, 30), (17, 90), (18, 365)):
        hh = bh[max(0, kd - w + 1):kd + 1].max(); ll = bl[max(0, kd - w + 1):kd + 1].min()
        pos = (px - ll) / (hh - ll) if hh > ll else 0.5; f[c_] = pos if S > 0 else 1 - pos
    v24 = V1[max(j - 23, 0):j + 1].sum(); v20 = V1[max(j - 479, 0):j + 1].sum() / 20
    f[19] = np.log((v24 + 1e-9) / (v20 + 1e-9))
    f[20] = np.nan_to_num((wilder_atr(H1, L1, C1) / C1 * 100)[j] / max(dat, 1e-9))
    lr = lambda x, k: np.log(x[j] / x[j - k]) if j - k >= 0 else np.nan
    f[21] = S * np.nan_to_num(lr(M["oi"], 4)) * 100; f[22] = S * np.nan_to_num(lr(M["oi"], 24)) * 100
    f[25] = S * np.nan_to_num(M["fund"][j]) * 1e4
    r1 = np.full(len(C1), np.nan); r1[1:] = np.log(C1[1:] / C1[:-1]); b1 = np.full(len(C1), np.nan); b1[1:] = np.log(bC[1:] / bC[:-1])
    Wb = 24 * 60
    x = np.nan_to_num(r1 * b1); yv = np.nan_to_num(b1 * b1); cx = np.concatenate([[0], np.cumsum(x)]); cy = np.concatenate([[0], np.cumsum(yv)])
    nn = len(C1); beta = np.ones(nn)
    beta[Wb:] = np.clip((cx[Wb:nn] - cx[:nn - Wb]) / np.maximum(cy[Wb:nn] - cy[:nn - Wb], 1e-12), 0, 3)
    r24 = np.full(nn, np.nan); r24[24:] = np.log(C1[24:] / C1[:-24]); b24 = np.full(nn, np.nan); b24[24:] = np.log(bC[24:] / bC[:-24])
    resid = r24 - beta * b24; c2 = np.concatenate([[0], np.cumsum(np.nan_to_num(resid) ** 2)])
    if j >= Wb:
        sd = np.sqrt((c2[j] - c2[j - Wb]) / Wb); f[26] = S * np.nan_to_num(resid[j] / sd if sd > 0 else np.nan)
    vm = V1[max(j - 480, 0):j].mean(); f[27] = np.nan_to_num(np.log(max(V1[j] / max(vm, 1e-12), 1e-6)))
    rg = H1[j] - L1[j]
    f[28] = np.nan_to_num(((min(O1[j], C1[j]) - L1[j]) if S > 0 else (H1[j] - max(O1[j], C1[j]))) / rg) if rg > 0 else 0.0
    eds = [abs(ema(dC, k)[dpi_j - 1] - px) / dpx for k in (7, 14, 28, 50, 100, 200)]
    eds = [e for e in eds if np.isfinite(e)]
    f[30] = min(min(eds) if eds else 99, 20)
    return f
if __name__ == "__main__":
    L = json.load(open("cfl_bt_v1.json"))
    from bt_trades import gate_sym
    sp = json.load(open("lv/split.json")); inv = {gate_sym(s)[0]: s for s in sp["bot"]}
    rng = np.random.default_rng(3); picks = [L[i] for i in rng.choice(len(L), 60, replace=False)]
    ev_ok = 0; worst = np.zeros(31); n = 0; bad = []
    for p in picks:
        sym = inv[p["s"]]; tsig = p["t"] - 3600; fam = E3.FAMS.index(p["lvl"]); side = -p["d"]
        evs = events_at(sym, tsig)
        if (fam, side) in evs: ev_ok += 1
        else: bad.append((sym, p["lvl"], str(np.datetime64(tsig, "s"))))
        z = np.load(f"ev3/{sym}.npz"); k = np.flatnonzero((z["t"] == tsig) & (z["fam"] == fam) & (z["side"] == side))
        if not len(k): continue
        fb = feats(sym, tsig, fam, side); fr = z["F"][k[0]].astype(float)
        for c in ("ls_z", "tk_z", "top_z"): fr[E2.FNAMES.index(c)] = 0.0
        worst = np.maximum(worst, np.abs(fb - fr)); n += 1
    print(f"события (окна бота 1h {W1}, 4h {W4}, 1d {WD}): {ev_ok} из {len(picks)}; не нашлись: {bad[:6]}")
    print("признаки: макс. расхождение", {E2.FNAMES[i]: round(float(worst[i]), 4) for i in range(31) if worst[i] > 1e-3}, "на", n)
