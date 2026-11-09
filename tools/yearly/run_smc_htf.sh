#!/bin/bash
# the yearly fallback — 🧱 SMC and 📏 HTF (one lab: the levels' events lv2 on the clean 2020- candles of the 210 coins): the candles
# (zones_model/dl.py — the 127, then the 83 of coins83.txt; fill_gaps.py), the events (lv_engine.py), each model's retrain with its
# checks (yearly_smc.py, yearly_htf.py), then the bot's tests with each new file (a failed test -> not accepted).
# -> $OUT/smc_report.json, $OUT/htf_report.json (+ the model files when accepted). usage: YEAR=2027 END=2026-12 OUT=dir bash run_smc_htf.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd); R=$(cd "$HERE/.." && pwd); WR="$R/winrate"; ROOT=$(cd "$R/.." && pwd)
export PYTHONPATH="$WR:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation" ALLSUF=_clr
WORK=${WORK:-/home/user/smcwork}; mkdir -p "$OUT" "$WORK/c"
step() { local log=$1; shift; "$@" > "$log" 2>&1 || { echo "ОШИБКА шага ($*):"; tail -40 "$log"; exit 1; }; }
SECONDS=0; cd "$WORK/c"
step "$OUT/smc_dl127.log" env END=$END python3 "$R/zones_model/dl.py" 1h
step "$OUT/smc_dl83.log" env END=$END DL_COINS="$HERE/coins83.txt" python3 "$R/zones_model/dl.py" 1h
step "$OUT/smc_fill.log" python3 "$R/zones_model/fill_gaps.py" data/1h
echo "свечи 210 монет с 2020: $(ls data/1h | wc -l) файлов, ${SECONDS}s"
export LV_D1H="$WORK/c/data/1h" LV_OUT="$WORK/lv2" LVDIR="$WORK/lv2"
cd "$WR"
step "$OUT/smc_lv.log" python3 "$R/new_ind/lv_engine.py" $(python3 -c "import json;s=json.load(open('lv/split.json'));print(' '.join(s['bot']+s['chk']))")
echo "события уровней: ${SECONDS}s"
test_model() {   # name, model file, tests…: the new file in the checkout, the tests, the old file back; a failure -> the report says so
  local key=$1 fn=$2; shift 2; local fails=""
  cp "$ROOT/$fn" "$OUT/$fn.old"; cp "$OUT/$fn" "$ROOT/$fn"
  for t in "$@"; do
    YEARLY_NEW_MODEL=1 python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv=['$t.py']; exec(compile(open('$t.py').read(), '$t.py', 'exec'), {'__file__': '$WR/$t.py', '__name__': '__main__'})" > "$OUT/$t.log" 2>&1 || true
    out=$(grep -E "^FAIL|ALL OK|FAILED|$t (OK|FAIL)" "$OUT/$t.log" | tail -3); echo "$t: $out"
    if echo "$out" | grep -qE "ALL OK|$t OK" && ! echo "$out" | grep -qE "^FAIL|FAILED"; then :; else fails="$fails $t"; echo "--- $t, хвост:"; grep -vE "^\[ERR\]|^127\.0|GET /|Warning" "$OUT/$t.log" | tail -25; fi
  done
  cp "$OUT/$fn.old" "$ROOT/$fn"
  python3 - "$OUT/${key}_report.json" "$fails" <<'P'
import sys, json
fn, fails = sys.argv[1], sys.argv[2].split()
r = json.load(open(fn)); r["checks"]["C"] = {"failed": fails}
if fails:
    r["ok"] = False; r["why"] = "тесты бота с новой моделью не прошли: " + ", ".join(fails)
json.dump(r, open(fn, "w"), indent=1)
print(("ПРИНЯТО: " if r["ok"] else "НЕ ПРИНЯТО: ") + r["why"])
P
}
set +e
python3 "$HERE/yearly_smc.py"; rs=$?
python3 "$HERE/yearly_htf.py"; rh=$?
set -e
[ $rs -eq 0 ] && test_model smc vp_smc_model.json t_smc_v6 t_smc_bot
[ $rh -eq 0 ] && test_model htf vp_htf_model.json t_htf_v3 t_htf_bot
echo "SMC и HTF: ${SECONDS}s"
