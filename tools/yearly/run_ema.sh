#!/bin/bash
# the yearly fallback — 📐 EMA: the 127 coins' 1h candles from 2020 (zones_model/dl.py), the touches rebuilt (er_build -> er_df ->
# er_lab3 -> er_pen), the retrain with its checks (yearly_ema.py), the bot's test t_emx_v13 with the new file.
# -> $OUT/ema_report.json (+ vp_ema_model.json when accepted). usage: YEAR=2027 END=2026-12 OUT=dir bash run_ema.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd); R=$(cd "$HERE/.." && pwd); WR="$R/winrate"; EM="$R/ema_model"; ROOT=$(cd "$R/.." && pwd)
mkdir -p "$OUT"
step() { local log=$1; shift; "$@" > "$log" 2>&1 || { echo "ОШИБКА шага ($*):"; tail -40 "$log"; exit 1; }; }
SECONDS=0; cd "$EM"
step "$OUT/ema_dl.log" env END=$END python3 ../zones_model/dl.py 1h
for s in er_build er_df er_lab3 er_pen; do step "$OUT/ema_$s.log" python3 $s.py; done
echo "касания EMA: ${SECONDS}s"
set +e; python3 "$HERE/yearly_ema.py"; rc=$?; set -e
[ $rc -eq 0 ] || exit 0
cp "$ROOT/vp_ema_model.json" "$OUT/vp_ema_model.old.json"; cp "$OUT/vp_ema_model.json" "$ROOT/vp_ema_model.json"
cd "$WR"; export PYTHONPATH="$WR:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation"
YEARLY_NEW_MODEL=1 python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv=['t_emx_v13.py']; exec(compile(open('$EM/t_emx_v13.py').read(), 't_emx_v13.py', 'exec'), {'__file__': '$EM/t_emx_v13.py', '__name__': '__main__'})" > "$OUT/t_emx_v13.log" 2>&1 || true
cp "$OUT/vp_ema_model.old.json" "$ROOT/vp_ema_model.json"
out=$(grep -E "^FAIL|t_emx_v13 (OK|FAIL)" "$OUT/t_emx_v13.log" | tail -3); echo "t_emx_v13: $out"
fails=""; echo "$out" | grep -q "t_emx_v13 OK" && ! echo "$out" | grep -q "^FAIL" || { fails="t_emx_v13"; grep -vE "^\[ERR\]|Warning" "$OUT/t_emx_v13.log" | tail -25; }
python3 - "$OUT/ema_report.json" "$fails" <<'P'
import sys, json
fn, fails = sys.argv[1], sys.argv[2].split()
r = json.load(open(fn)); r["checks"]["C"] = {"failed": fails}
if fails:
    r["ok"] = False; r["why"] = "тесты бота с новой моделью не прошли: " + ", ".join(fails)
json.dump(r, open(fn, "w"), indent=1)
print(("ПРИНЯТО: " if r["ok"] else "НЕ ПРИНЯТО: ") + r["why"])
P
echo "EMA: ${SECONDS}s"
