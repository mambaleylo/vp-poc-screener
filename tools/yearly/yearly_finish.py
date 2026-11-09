"""The yearly fallback's last step: each model's artifact (<arts>/<model>/<model>_report.json, its vp_*_model.json when accepted)
-> the accepted files into the checkout's root (the workflow commits them to main), a line per model into YEARLY_LOG.md, and the
report (markdown, Russian; its first line — the summary) on stdout. usage: yearly_finish.py <arts dir> "<the gate's reason>" """
import os, sys, json, time, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
ARTS, WHY = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
NAMES = {"cfl": ("🔄 Классика", "vp_cfl_model.json"), "dlm": ("⚡ Лимитки", "vp_dlm_model.json"), "smc": ("🧱 SMC", "vp_smc_model.json"),
         "htf": ("📏 HTF", "vp_htf_model.json"), "ema": ("📐 EMA", "vp_ema_model.json")}
DONE = ("cfl", "smc", "htf", "ema", "dlm")   # the models whose recipe the fallback runs (the rest: not moved here yet — they stay)
rows, acc = [], []
for k, (nm, fn) in NAMES.items():
    import glob
    rp = (glob.glob(os.path.join(ARTS, "*", f"{k}_report.json")) + [os.path.join(ARTS, k, f"{k}_report.json")])[0]
    adir = os.path.dirname(rp)
    if k not in DONE:
        rows.append((nm, "—", "рецепт ещё не перенесён в запасной вариант — модель прежняя")); continue
    if not os.path.exists(rp):
        rows.append((nm, "❌", "шаг сломался (нет отчёта) — модель прежняя")); continue
    r = json.load(open(rp))
    if r.get("ok") and os.path.exists(os.path.join(adir, fn)):
        shutil.copy(os.path.join(adir, fn), os.path.join(ROOT, fn)); acc.append(nm)
        rows.append((nm, "✅", r.get("why", "")))
    else:
        rows.append((nm, "⏸", (r.get("why") or "не принято") + " — модель прежняя"))
head = (f"переобучены: {', '.join(acc)}" if acc else "ничего не переобучено") + f" ({len(acc)} из {len(NAMES)})"
out = [head, "", f"Почему запасной вариант: {WHY}", "", "| Модель | Итог | Подробности |", "|---|---|---|"] + [f"| {a} | {b} | {c} |" for a, b, c in rows]
out += ["", "Принятые модели бот возьмёт из main в течение суток и напишет в Telegram. Остальные работают как раньше.",
        "Строгие правила: нынешняя модель воспроизвелась её рецептом, есть новый год данных, новая модель не сломана, тесты бота прошли."]
log = os.path.join(HERE, "YEARLY_LOG.md")
with open(log, "a") as f:
    f.write(f"\n## {time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC — {head}\n" + "\n".join(f"- {a}: {b} {c}" for a, b, c in rows) + "\n")
print("\n".join(out))
