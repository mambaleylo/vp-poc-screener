"""The yearly retrain's fallback gate (the user: "запасной вариант — сразу, если основной не срабатывает"). The main way: the
claude.ai task in the chat on 5 January (RETRAIN.md) — its first step writes {"year", "started"} to status.json on the branch
yearly-status, and {"prepared"} once the new models wait for the user's «да». This gate (GitHub Actions, 5 January 1.5 h after
the task, then daily to the 15th) -> run the fallback (exit 0, prints "run") or not (exit 3, prints why):
  every yearly model already trained to the year's end in main -> no (done);
  the fallback already ran this year -> no;
  "prepared" this year -> no (the models wait for the user's answer — not a failure);
  "started" this year less than 24 h ago -> no (still working);
  else (never started: the session did not start; or started > 24 h ago and nothing prepared: stuck / broke) -> run.
usage: yearly_gate.py <status.json or ""> [now unix]"""
import sys, os, json, time, calendar
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
MODELS = {"dlm": "vp_dlm_model.json", "smc": "vp_smc_model.json", "htf": "vp_htf_model.json", "cfl": "vp_cfl_model.json", "ema": "vp_ema_model.json"}


def trained(fn):
    """the model's oldest training end (⚡: its streams with a date too)"""
    m = json.load(open(os.path.join(ROOT, fn)))
    ds = [m.get("trained_to")] + [s.get("trained_to") for s in m.get("streams") or [] if s.get("trained_to")]
    ds = [int(x) for x in ds if x]
    return min(ds) if ds else 0


def gate(st, now):
    g = time.gmtime(now); year = int(os.environ.get("YEAR") or g.tm_year)   # the run's year (a manual run may give it): the data to 31 December of year - 1
    need = calendar.timegm((year - 1, 12, 10, 0, 0, 0))   # the recipes cut 14 days before the end: 18 December -> trained
    old = {k: trained(fn) for k, fn in MODELS.items()}
    if all(v >= need for v in old.values()):
        return False, "все годовые модели уже обучены по конец года — делать нечего"
    st = st if (st or {}).get("year") == year else {}
    if st.get("fallback"):
        return False, f"запасной вариант уже запускался ({time.strftime('%d.%m %H:%M', time.gmtime(st['fallback']))} UTC)"
    if st.get("prepared"):
        return False, "основной путь подготовил модели — ждут «да» пользователя в чате"
    if st.get("started") and now - st["started"] < 24 * 3600:
        return False, f"основной путь работает с {time.strftime('%d.%m %H:%M', time.gmtime(st['started']))} UTC — ждём до суток"
    why = ("основной путь начал и за сутки не подготовил модели (завис или упал)" if st.get("started")
           else "основной путь не начинал (сессия не запустилась)")
    return True, why + "; не обучены по конец года: " + ", ".join(k for k, v in old.items() if v < need)


if __name__ == "__main__":
    st = {}
    if len(sys.argv) > 1 and sys.argv[1] and os.path.exists(sys.argv[1]):
        st = json.load(open(sys.argv[1]))
    now = int(sys.argv[2]) if len(sys.argv) > 2 else int(time.time())
    run, why = gate(st, now)
    print(("run: " if run else "skip: ") + why)
    sys.exit(0 if run else 3)
