"""a GIF for the user: how a ⚡ trade is set on the chart — the 2h stream's limit 2 ATR under the close, the stop by the
close 2 ATR under, the exchange's emergency stop 3 ATR, the take 1.1 ATR — and the risk -> size -> leverage -> margin.
usage: gif_dlm.py OUT.gif"""
import sys, io, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["text.parse_math"] = False
from matplotlib.patches import Rectangle
from PIL import Image
OUT = sys.argv[1] if len(sys.argv) > 1 else "dlm.gif"
BG, FG, DIM = "#0f1419", "#e6e6e6", "#8a96a3"
UP, DN, LIM, SL, HS, TP = "#26a69a", "#ef5350", "#42a5f5", "#ff7043", "#b71c1c", "#66bb6a"
rng = np.random.default_rng(7)
# 30 past candles drifting down to the close 1.000, then the dip to the limit and the bounce to the take
cl = 1.05 + np.cumsum(rng.normal(-0.001, 0.009, 30)); cl += (1.0 - cl[-1]) * np.arange(30) / 29   # a walk ending at the close 1.000
op = np.r_[1.05, cl[:-1]]; cs = []
for o_, c in zip(op, cl):
    cs.append((o_, max(o_, c) + abs(rng.normal(0, 0.005)), min(o_, c) - abs(rng.normal(0, 0.005)), c))
FUT = [(1.000, 1.004, 0.978, 0.982), (0.982, 0.986, 0.955, 0.966), (0.966, 0.975, 0.958, 0.971), (0.971, 0.979, 0.966, 0.976), (0.976, 0.986, 0.972, 0.984)]
E, ATR = 0.960, 0.02
LV = dict(lim=E, sl=E - 2 * ATR, hs=E - 3 * ATR, tp=E + 1.1 * ATR)
EQ, RK = 200.0, 4.5 * 0.625
RD = EQ * RK / 100; DIST = (E - LV["sl"]) / E; NOT = RD / DIST; QTY = NOT / E; LEV = min(50, 20, 14); MG = NOT / LEV
WIN = QTY * (LV["tp"] - E); HSL = QTY * (E - LV["hs"])
def frame(n_fut, show, title, body, calc=None, hl=None):
    fig = plt.figure(figsize=(7.2, 10), dpi=100, facecolor=BG)
    ax = fig.add_axes([0.09, 0.42, 0.66, 0.50], facecolor=BG)
    C = cs + FUT[:n_fut]
    for i, (op, hi, lo, cl) in enumerate(C):
        col = UP if cl >= op else DN
        ax.plot([i, i], [lo, hi], color=col, lw=1.2, zorder=2)
        ax.add_patch(Rectangle((i - 0.33, min(op, cl)), 0.66, max(abs(cl - op), 0.0015), color=col, zorder=3))
    x1 = 37
    def line(k, col, txt, ls="-"):
        if k in show:
            ax.plot([28, x1], [LV[k]] * 2, color=col, lw=2.4 if k in (hl or ()) else 1.6, ls=ls, zorder=4)
            ax.text(x1 + 0.3, LV[k], f"{txt}\n{LV[k]:.3f}$", color=col, va="center", fontsize=10.5, fontweight="bold")
    line("tp", TP, "тейк"); line("lim", LIM, "лимитка"); line("sl", SL, "стоп", "--"); line("hs", HS, "авар. стоп", ":")
    if "close" in show:
        ax.annotate("закрытие 1.000$", (29, 1.0), (21.5, 1.035), color=FG, fontsize=10.5, arrowprops=dict(arrowstyle="->", color=FG))
    if "atr" in show:
        ax.annotate("", (31.2, 1.0), (31.2, 0.98), arrowprops=dict(arrowstyle="<->", color="#ffca28", lw=1.6))
        ax.text(31.6, 0.99, "1 ATR\n0.02$", color="#ffca28", fontsize=10, va="center")
        if "lim" in show:
            ax.annotate("", (33.2, 1.0), (33.2, E), arrowprops=dict(arrowstyle="<->", color="#ffca28", lw=1.6))
            ax.text(33.5, 0.975, "2 ATR", color="#ffca28", fontsize=10, va="center")
    if "fill" in show:
        ax.scatter([31], [E], s=160, color=LIM, edgecolor="white", zorder=6); ax.text(31, E - 0.012, "куплено", color=LIM, ha="center", fontsize=10)
    if "win" in show:
        ax.scatter([34], [LV["tp"]], s=160, color=TP, edgecolor="white", zorder=6); ax.text(34, LV["tp"] + 0.009, f"+{WIN:.2f}$", color=TP, ha="center", fontsize=12, fontweight="bold")
    ax.set_xlim(8, 37); ax.set_ylim(0.885, 1.075); ax.tick_params(colors=DIM, labelsize=9); ax.set_xticks([]); ax.set_yticks(np.arange(0.90, 1.071, 0.02))
    for s in ax.spines.values(): s.set_color("#2a333d")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    fig.text(0.05, 0.965, "Как бот ставит сделку ⚡ (2ч-поток, лонг)".replace("⚡ ", ""), color=FG, fontsize=15, fontweight="bold")
    fig.text(0.05, 0.937, "пример: счёт 200$, монета по 1$, ATR 0.02$", color=DIM, fontsize=11)
    fig.text(0.05, 0.375, title, color="#ffca28", fontsize=14.5, fontweight="bold")
    fig.text(0.05, 0.345, body, color=FG, fontsize=12.5, va="top", linespacing=1.45)
    if calc and "nocalc" not in show:
        y = 0.19
        for i, (k, v) in enumerate(calc):
            on = hl == ("c", i)
            fig.text(0.07, y - i * 0.034, k, color=FG if on else DIM, fontsize=12, fontweight="bold" if on else "normal")
            fig.text(0.93, y - i * 0.034, v, color="#ffca28" if on else DIM, fontsize=12, ha="right", fontweight="bold" if on else "normal")
    b = io.BytesIO(); fig.savefig(b, format="png", facecolor=BG); plt.close(fig); b.seek(0)
    return Image.open(b).convert("RGB")
CALC = [("1. Риск: 200$ × 4.5% × 0.625", f"{RD:.2f}$ на стопе"),
        ("2. До стопа: 0.960 → 0.920", f"{DIST * 100:.2f}%"),
        (f"3. Позиция: {RD:.2f}$ / {DIST * 100:.2f}%", f"{NOT:.0f}$ ({QTY:.1f} монет)"),
        ("4. Плечо: min(монета 50x, аккаунт 20x, бот 14x)", f"{LEV}x"),
        (f"5. Маржа: {NOT:.0f}$ / {LEV}", f"{MG:.2f}$")]
F = []   # (image, ms)
add = lambda ms, *a, **k: F.append((frame(*a, **k), ms))
add(3000, 0, {"close"}, "1. Свеча закрылась", "Это 2-часовой график монеты.\nПоследняя свеча закрылась на 1.000$.")
add(3500, 0, {"close", "atr"}, "2. ATR — обычный размах свечи", "Бот меряет, на сколько монета обычно ходит\nза свечу. Здесь ATR = 0.02$ (2%).\nВсе уровни сделки считаются в ATR.")
add(4000, 0, {"close", "atr", "lim"}, "3. Лимитка на 2 ATR ниже", "Модель решила, что вход хороший.\nЛимитка на покупку: 1.000 − 2 × 0.02 = 0.960$.\nКупим, только если цена сама упадёт туда.", hl=("lim",))
add(4500, 0, {"lim", "sl"}, "4. Стоп 0.920$ (2 ATR ниже входа)", "Стоп по закрытию: срабатывает, только если\nсвеча ЗАКРОЕТСЯ ниже 0.920$.\nТень ниже и возврат — не выбьет.", hl=("sl",))
add(4000, 0, {"lim", "sl", "hs"}, "5. Аварийный стоп на бирже 0.900$", "3 ATR ниже входа. Страховка от резкого\nобвала — стоит на Binance, даже если\nтелефон выключен.", hl=("hs",))
add(3500, 0, {"lim", "sl", "hs", "tp"}, "6. Тейк 0.982$ (1.1 ATR выше входа)", "Цель небольшая: такие откаты чаще\nдоходят до тейка, чем до стопа.", hl=("tp",))
ALL = {"lim", "sl", "hs", "tp"}
add(4500, 0, ALL, "7. Сколько рисковать", f"Риск ⚡ 4.5% счёта, × 0.625 пока открыто\nменьше 5 сделок → {RK:.2f}%.\nЕсли сработает стоп — потеряем {RD:.2f}$.", CALC, hl=("c", 0))
add(4000, 0, ALL, "8. Расстояние до стопа", f"От входа 0.960$ до стопа 0.920$ —\n{DIST * 100:.2f}% цены.", CALC, hl=("c", 1))
add(5000, 0, ALL, "9. Размер позиции", f"Чтобы на стопе потерять ровно {RD:.2f}$,\nпозиция = {RD:.2f}$ / {DIST * 100:.2f}% = {NOT:.0f}$.\nЭто {QTY:.1f} монет по 0.960$.", CALC, hl=("c", 2))
add(5500, 0, ALL, "10. Плечо", "Берётся меньшее из трёх: сколько даёт\nмонета на Binance, лимит аккаунта (20x\nпервые 30 дней) и потолок бота 14x.", CALC, hl=("c", 3))
add(6500, 0, ALL, "11. Маржа", f"Бирже нужно заморозить {NOT:.0f}$ / {LEV} = {MG:.2f}$.\nПлечо НЕ меняет убыток на стопе ({RD:.2f}$):\nпри 10x маржа была бы {NOT / 10:.2f}$, при 14x — {MG:.2f}$.\nМеньше маржи — больше места другим сделкам.", CALC, hl=("c", 4))
add(900, 1, ALL, "Ждём…", "Цена идёт вниз к лимитке.", CALC)
add(4000, 2, ALL | {"fill"}, "12. Лимитка исполнилась", f"Тень дошла до 0.960$ — куплено {QTY:.1f} монет\nна {NOT:.0f}$ (маржа {MG:.2f}$).\nСтоп и тейк уже стоят.", CALC, hl=("lim",))
add(900, 3, ALL | {"fill"}, "Ждём…", "Цена отскакивает.", CALC)
add(900, 4, ALL | {"fill"}, "Ждём…", "Цена отскакивает.", CALC)
add(5000, 5, ALL | {"fill", "win"}, f"13. Тейк: +{WIN:.2f}$", f"Цена дошла до 0.982$ — прибыль +{WIN:.2f}$\n(+{WIN / EQ * 100:.1f}% счёта, без учёта комиссий).", CALC, hl=("tp",))
add(9000, 5, ALL | {"nocalc"}, "А если бы не повезло", f"• Свеча закрылась ниже 0.920$ → выход, −{RD:.2f}$\n• Резкий прокол до 0.900$ → аварийный стоп, −{HSL:.2f}$\n• Ни тейка, ни стопа за 32 свечи → выход по рынку\n• Шорт — всё зеркально (шорты 2ч-потока с риском ×0.5)\n• 4ч-поток: лимитка на 1 ATR за тенью 4ч-свечи", CALC)
im0 = F[0][0]
im0.save(OUT, save_all=True, append_images=[f for f, _ in F[1:]], duration=[ms for _, ms in F], loop=0, optimize=True)
print(OUT, len(F), "frames", f"risk {RD:.2f} notional {NOT:.1f} qty {QTY:.1f} lev {LEV} margin {MG:.2f} win {WIN:.2f} hsl {HSL:.2f}")
