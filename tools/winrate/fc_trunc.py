"""look-ahead test of the classic events (ev3) — the truncation test: for a sample of the opposite-side classic's taken
trades, the coin's 1h bars (and BTC's) cut right after the signal bar J, plus a fake bar J+1 carrying only its open (the
entry price, known at the entry); the engine re-run on that -> the event (J, fam, side) must be there with the same
features. Any use of a later bar (an Ichimoku span shifted the wrong way, an unconfirmed pivot, the forming day's ATR,
BTC's next bar...) would change or drop it."""
import sys, os, json, tempfile, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
import lv_engine as LE, ev2_engine as E2, ev3_engine as E3
FULL = {}
def full(sym):
    if sym not in FULL: FULL[sym] = LE.load_np(sym)
    return FULL[sym]
CUT = {"t": None}
def cut_load(sym):
    T, O, H, L, C, V = full(sym)
    j = int(np.searchsorted(T, CUT["t"]))          # bars with T < t_cut (= the signal bar J and before)
    if sym == "BTCUSDT": return T[:j].copy(), O[:j].copy(), H[:j].copy(), L[:j].copy(), C[:j].copy(), V[:j].copy()
    T2, O2, H2, L2, C2, V2 = (a[:j + 1].copy() for a in (T, O, H, L, C, V))
    H2[-1] = L2[-1] = C2[-1] = O2[-1]; V2[-1] = 0.0                # the entry bar: its open only
    return T2, O2, H2, L2, C2, V2
E2.load_np = cut_load
tmp = tempfile.mkdtemp(); E2.OUT[0] = tmp
sp = json.load(open("lv/split.json"))
from bt_trades import gate_sym
inv = {}
for s in sp["bot"] + sp["chk"]: inv[gate_sym(s)[0]] = s
picks = []
for fn in ("fc_f_180_0.995.json", "fc_f_180_0.995_chk.json"):
    L = json.load(open(fn)); rng = np.random.default_rng(5); picks += [L[i] for i in rng.choice(len(L), 20, replace=False)]
ok = bad = 0; worst = 0.0
for p in picks:
    sym = inv[p["s"]]; z = np.load(f"ev3/{sym}.npz"); tsig = p["t"] - 3600
    k = np.flatnonzero((z["t"] == tsig) & (z["fam"] == p["fam"]))
    if not len(k): print("  нет в полном файле", sym, tsig); bad += 1; continue
    k = k[0]; J = int(z["j"][k])
    T = full(sym)[0]; CUT["t"] = int(T[J]) + 3600
    E2._B.clear()
    for b in ("_BTC", "BTC"):
        if hasattr(E2, b) and isinstance(getattr(E2, b), dict): getattr(E2, b).clear()
    fn = f"{tmp}/{sym}.npz"
    if os.path.exists(fn): os.remove(fn)
    E2.run(sym)
    if not os.path.exists(fn): print("  движок ничего не нашёл", sym); bad += 1; continue
    zc = np.load(fn); m = np.flatnonzero((zc["j"] == J) & (zc["fam"] == z["fam"][k]) & (zc["side"] == z["side"][k]))
    if not len(m): print(f"  ✗ {sym} {E3.FAMS[z['fam'][k]]}: событие пропало при обрезке"); bad += 1; continue
    d = np.nanmax(np.abs(np.nan_to_num(zc["F"][m[0]], nan=-999) - np.nan_to_num(z["F"][k], nan=-999)))
    dd = abs(float(zc["datr"][m[0]]) - float(z["datr"][k]))
    worst = max(worst, d, dd)
    if d > 1e-4 or dd > 1e-6:
        bad += 1; diff = np.flatnonzero(np.abs(np.nan_to_num(zc["F"][m[0]], nan=-999) - np.nan_to_num(z["F"][k], nan=-999)) > 1e-4)
        print(f"  ✗ {sym} {E3.FAMS[z['fam'][k]]}: признаки отличаются {[E2.FNAMES[i] for i in diff]} (Δ {d:.4f}), datr Δ {dd:.6f}")
    else: ok += 1
print(f"обрезка: совпало {ok} из {len(picks)}, расхождений {bad}, max|Δ| {worst:.2e}")
