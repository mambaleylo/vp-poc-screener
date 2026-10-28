"""The bot for the tests: vp_poc_screener.py imported from a copy in a temp folder (its state / settings / model files are
written there, never into the repo), with the repo's model files and backtest list copied next to it. The backtest list
is read-only: bt_trades() never downloads (a test must not replace the list with the GitHub one). Run a test from any
folder: python3 tools/winrate/t_xxx.py"""
import os, sys, glob, json, shutil, tempfile, importlib.util

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TMP = tempfile.mkdtemp(prefix="vpbot_")
shutil.copy(os.path.join(REPO, "vp_poc_screener.py"), TMP)
for fn in glob.glob(os.path.join(REPO, "vp_*_model.json")) + [os.path.join(REPO, "vp_bt_trades.json"), os.path.join(REPO, ".gitignore")]:
    if os.path.exists(fn):
        shutil.copy(fn, TMP)
os.environ.setdefault("VP_TELEGRAM_ENABLED", "0")
_spec = importlib.util.spec_from_file_location("vp_poc_screener", os.path.join(TMP, "vp_poc_screener.py"))
V = importlib.util.module_from_spec(_spec)
sys.modules["vp_poc_screener"] = V
_spec.loader.exec_module(V)

V._bt_trades_real = V.bt_trades   # the bot's own (t_bt_refetch)
_BTD = json.load(open(os.path.join(TMP, "vp_bt_trades.json")))


def _bt_trades(need=None):
    V._bt_cache.update({"d": _BTD, "t": 1e18})
    return _BTD


V.bt_trades = _bt_trades

# the research data (Binance 1h candles, data/1h/<SYM>.csv: t,o,h,l,c,v) — next to this file when the research folder is
# here; the tests that re-make backtest trades on the candles need it
D = os.path.dirname(os.path.abspath(__file__))


def load(bsym):
    fn = os.path.join(D, "data", "1h", f"{bsym}.csv")
    if not os.path.exists(fn):
        return None
    out = []
    for line in open(fn):
        p = line.strip().split(",")
        if len(p) >= 6:
            out.append({"time": int(float(p[0])), "open": float(p[1]), "high": float(p[2]), "low": float(p[3]), "close": float(p[4]), "volume": float(p[5])})
    return out
