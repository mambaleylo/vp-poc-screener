"""P/R's monthly retrain decides itself (the user: "если можно без да, пусть само сравнивает и принимает решение"): the new model
(prv_month.py) goes to the bot only if ALL hold — (A) the deployed model is reproduced on the same data (prv_repro.py: the scores'
correlation >= 0.99 a side, the over-threshold overlap >= 80%), (B) a new month of data (trained_to >= the old + 20 days), (C) the
bot's test with the new file (t_prx_e2e.py: every event, feature, score and trade the same), (D) the new model sane (finite
thresholds; the last month's signals a side <= 5 x its own monthly average + 3). Accepted -> vp_prv_model.json replaced, a line in
RETRAIN_LOG.md; rejected -> nothing changed, the reason in RETRAIN_LOG.md, exit 2. usage: PRV_OUT=… prv_decide.py [--apply]"""
import os, sys, json, math, shutil, subprocess, tempfile, datetime as dt, re
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.environ.get("PRV_OUT", "/home/user/prv_month"); LAB = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
C1H = os.environ.get("PRV_C1H", os.path.join(HERE, "..", "ema_model", "data", "1h"))
D_ = lambda t: dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%d")
why, info = [], {}
rp = json.load(open(f"{OUT}/prv_repro.json")); cm = json.load(open(f"{OUT}/prv_month_cmp.json")); N = json.load(open(f"{OUT}/vp_prv_model.json"))
O = json.load(open(f"{REPO}/vp_prv_model.json"))
for s in ("1", "-1"):   # (A)
    r = rp[s]; ov = r["both"] / max(1, max(r["rebuilt"], r["bot"]))
    info[f"repro{s}"] = f"корреляция {r['corr']:.4f}, совпадение {ov * 100:.0f}%"
    if not (r["corr"] >= 0.99 and ov >= 0.8): why.append(f"нынешняя модель не воспроизвелась (сторона {s}: {info['repro' + s]})")
if int(N["trained_to"]) < int(O["trained_to"]) + 20 * 86400: why.append(f"нет нового месяца данных ({D_(N['trained_to'])} против {D_(O['trained_to'])})")   # (B)
for s in ("1", "-1"):   # (D)
    c = cm["cmp"][s]
    if not all(math.isfinite(float(x)) for x in (N["thr"][s],)): why.append(f"порог стороны {s} не число")
    if c["new"] > 5 * c["new_month_avg"] + 3: why.append(f"сторона {s}: сигналов за месяц {c['new']} при среднем {c['new_month_avg']} — подозрительно много")
# (C) the bot's test on the new file: a folder like the lab's (common.py's D) with the candles, the funding, the events, the model
T = tempfile.mkdtemp(); shutil.copy(os.path.join(HERE, "..", "ema_model", "common.py"), T)
os.makedirs(f"{T}/data"); os.symlink(os.path.abspath(C1H), f"{T}/data/1h"); os.symlink(f"{LAB}/data/funding", f"{T}/data/funding")
os.symlink(f"{OUT}/prv_ev", f"{T}/prv_ev"); shutil.copy(f"{OUT}/vp_prv_model.json", f"{T}/vp_prv_model.json")
env = dict(os.environ, PYTHONPATH=":".join([T, HERE, os.path.join(HERE, "..", "neuro_model"), os.path.join(HERE, "..", "winrate")]))
r = subprocess.run([sys.executable, os.path.join(HERE, "t_prx_e2e.py")], env=env, capture_output=True, text=True, cwd=T, timeout=3600)
txt = r.stdout + r.stderr
m1 = re.search(r"events ok (\d+) off (\d+) miss (\d+) max score diff ([\d.e-]+)", txt); m2 = re.search(r"trades ok (\d+) diff (\d+)", txt)
if not (m1 and m2): why.append("тест бота не дошёл до конца: " + txt.strip().splitlines()[-1][:200] if txt.strip() else "тест бота не запустился")
else:
    info["test"] = f"события {m1.group(1)}/{int(m1.group(1)) + int(m1.group(2)) + int(m1.group(3))}, сделки {m2.group(1)}/{int(m2.group(1)) + int(m2.group(2))}"
    if int(m1.group(2)) or int(m1.group(3)) or int(m2.group(2)) or float(m1.group(4)) > 0.01: why.append(f"тест бота: расхождения ({info['test']}, оценка {m1.group(4)})")
ok = not why
c1, c2 = cm["cmp"]["1"], cm["cmp"]["-1"]
line = (f"| {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')} | данные по {D_(N['trained_to'])} | "
        f"пороги лонг {O['thr']['1']} -> {N['thr']['1']}, шорт {O['thr']['-1']} -> {N['thr']['-1']} | "
        f"сигналов за последний месяц: старая {c1['old'] + c2['old']}, новая {c1['new'] + c2['new']} | "
        f"{info.get('repro1', '')}; {info.get('test', '')} | " + ("**принята**" if ok else "не принята: " + "; ".join(why)) + " |")
print(line, flush=True)
if "--apply" in sys.argv:
    log = os.path.join(HERE, "RETRAIN_LOG.md")
    if not os.path.exists(log):
        open(log, "w").write("# P/R — ежемесячное переобучение (решает само, prv_decide.py)\n\n| запуск | обучено | пороги | сигналы | проверка | решение |\n|---|---|---|---|---|---|\n")
    open(log, "a").write(line + "\n")
    if ok: shutil.copy(f"{OUT}/vp_prv_model.json", f"{REPO}/vp_prv_model.json")
print("prv decide:", "accepted" if ok else "rejected", flush=True)
sys.exit(0 if ok else 2)
