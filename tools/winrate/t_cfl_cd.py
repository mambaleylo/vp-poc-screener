"""v0.99.778 — 🔄 Классика: the rule's pause after a coin's exit (cooldown_h 24, as the lab's busy = the exit + 24 h > the
signal hour): a new trade on the same coin & side within it is not opened, after it — opened; the other side / coin not held"""
import time
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
V.CFL_MODEL_FILE = "/home/user/vp-poc-screener/vp_cfl_model.json"; V._CFL["model"] = None
m = V.cfl_model(); r = m["rule"]
V.AUTOTRADE_ENABLED_CFL = False; V.TELEGRAM_ALERTS_CFL = False; V.cfl_save = lambda: None
H = 3600; t0 = (int(time.time()) // (4 * H) - 100) * 4 * H
def try_open(bsym, t_close, S=-1):
    n = len(V._CFL["trades"])
    V.cfl_open({"bsym": bsym, "fam": "bb_back_4h", "S": S, "score": 9.0, "datr": 4.0, "fill": 10.0, "live": 10.0}, t_close, m)
    return len(V._CFL["trades"]) > n
def closed(bsym, t_out, side=1):
    V._CFL["trades"] = [{"id": "c1", "bsym": bsym, "side": side, "status": "CLOSED", "t_in": t_out - 20 * H, "t_out": t_out}]
chk("в правиле пауза 24 ч", int(r.get("cooldown_h") or 0) == 24)
closed("SOLUSDT", t0); chk("через 20 ч после выхода — не открывается", not try_open("SOLUSDT", t0 + 20 * H))
closed("SOLUSDT", t0); chk("через 24 ч (сигнал часом раньше — 23 ч) — не открывается, как в лабе", not try_open("SOLUSDT", t0 + 24 * H))
closed("SOLUSDT", t0); chk("через 25 ч — открывается", try_open("SOLUSDT", t0 + 25 * H))
closed("SOLUSDT", t0); chk("другая монета — не держит", try_open("ETHUSDT", t0 + 4 * H))
closed("SOLUSDT", t0, side=-1); chk("та же монета, другая сторона — не держит", try_open("SOLUSDT", t0 + 4 * H))
print("t_cfl_cd OK" if ok else "t_cfl_cd FAIL")
