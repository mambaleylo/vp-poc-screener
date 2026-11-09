#!/bin/bash
# the yearly fallback — 🔄 Классика: the events and the label on the data to the year's end, the retrain with its checks
# (yearly_cfl.py), then the bot's tests with the new model file (a failed test -> not accepted). -> $OUT/cfl_report.json
# (+ $OUT/vp_cfl_model.json when accepted). usage: YEAR=2027 OUT=dir bash run_cfl.sh   (CUT_AT / MIN_DAYS: a rehearsal)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); WR="$HERE/../winrate"; ROOT=$(cd "$HERE/../.." && pwd)
export PYTHONPATH="$WR:$WR/../new_ind:$WR/../zones_model:$WR/../neuro_model:$WR/../adaptation" ALLSUF=_clr
mkdir -p "$OUT"; cd "$WR"
rm -rf ev3; SECONDS=0
step() { local log=$1; shift; "$@" > "$log" 2>&1 || { echo "ОШИБКА шага ($*):"; tail -40 "$log"; exit 1; }; }
step "$OUT/cfl_ev3.log" python3 ../new_ind/ev3_engine.py
step "$OUT/cfl_red.log" python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv = ['fc_red.py']; exec(open('fc_red.py').read())"
echo "события и метка: ${SECONDS}s"
set +e
python3 "$HERE/yearly_cfl.py"; rc=$?
set -e
[ $rc -eq 0 ] || exit 0   # not accepted: the report says why
cp "$ROOT/vp_cfl_model.json" "$OUT/vp_cfl_model.old.json"; cp "$OUT/vp_cfl_model.json" "$ROOT/vp_cfl_model.json"
fails=""
for t in t_cfl_v4 t_cfl_bot t_cfl_flt t_cfl_cd; do
  out=$(python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv=['$t.py']; exec(compile(open('$t.py').read(), '$t.py', 'exec'), {'__file__': '$WR/$t.py', '__name__': '__main__'})" 2>&1 | grep -E "^FAIL|ALL OK|FAILED|$t (OK|FAIL)" | tail -3)
  echo "$t: $out"
  echo "$out" | grep -qE "ALL OK|$t OK" && ! echo "$out" | grep -qE "^FAIL|FAILED" || fails="$fails $t"
done
cp "$OUT/vp_cfl_model.old.json" "$ROOT/vp_cfl_model.json"   # the checkout's file back: the finish job decides
python3 - "$OUT/cfl_report.json" "$fails" <<'P'
import sys, json
fn, fails = sys.argv[1], sys.argv[2].split()
r = json.load(open(fn)); r["checks"]["C"] = {"failed": fails}
if fails:
    r["ok"] = False; r["why"] = "тесты бота с новой моделью не прошли: " + ", ".join(fails)
json.dump(r, open(fn, "w"), indent=1)
print(("ПРИНЯТО: " if r["ok"] else "НЕ ПРИНЯТО: ") + r["why"])
P
