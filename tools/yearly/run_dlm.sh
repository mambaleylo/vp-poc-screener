#!/bin/bash
# the yearly fallback — ⚡ the 4h streams (wick4h, wick4h_o2; the 2h stream stays for the main way): the lab-store candles extended
# to the year's end (the workflow's step), the order features of the bot's 210 coins rebuilt for both streams (dlm_build.py
# BASE_ONLY), the retrain with its checks (yearly_dlm.py), the bot's tests with the new file.
# -> $OUT/dlm_report.json (+ vp_dlm_model.json when accepted). usage: YEAR=2027 OUT=dir LABSTORE=dir bash run_dlm.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd); R=$(cd "$HERE/.." && pwd); WR="$R/winrate"; ROOT=$(cd "$R/.." && pwd)
export PYTHONPATH="$WR:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation" ALLSUF=_clr
mkdir -p "$OUT"
step() { local log=$1; shift; "$@" > "$log" 2>&1 || { echo "ОШИБКА шага ($*):"; tail -40 "$log"; exit 1; }; }
SECONDS=0; cd "$WR"
rm -rf "$LABSTORE/feat/wick4h" "$LABSTORE/feat/wick4h_o2"   # rebuilt on the extended candles (dlm_build skips a file that exists)
step "$OUT/dlm_build.log" env BASE_ONLY=1 STREAMS=wick4h,wick4h_o2 python3 dlm_build.py 0 1
echo "признаки ⚡: $(ls "$LABSTORE/feat/wick4h" | wc -l) монет, ${SECONDS}s"
set +e; python3 -u "$HERE/yearly_dlm.py"; rc=$?; set -e
[ $rc -eq 0 ] || exit 0
cp "$ROOT/vp_dlm_model.json" "$OUT/vp_dlm_model.old.json"; cp "$OUT/vp_dlm_model.json" "$ROOT/vp_dlm_model.json"
fails=""
for t in ${DLM_TESTS:-t_dlm_bot t_dlm_o2 t_dlm_binance}; do
  YEARLY_NEW_MODEL=1 python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv=['$t.py']; exec(compile(open('$t.py').read(), '$t.py', 'exec'), {'__file__': '$WR/$t.py', '__name__': '__main__'})" > "$OUT/$t.log" 2>&1 || true
  out=$(grep -E "^FAIL|ALL OK|FAILED|$t .*OK|$t (OK|FAIL)" "$OUT/$t.log" | tail -3); echo "$t: $out"
  if echo "$out" | grep -qE "ALL OK| OK$" && ! echo "$out" | grep -qE "^FAIL|FAILED"; then :; else fails="$fails $t"; echo "--- $t, хвост:"; grep -vE "^\[ERR\]|^127\.0|GET /|Warning" "$OUT/$t.log" | tail -25; fi
done
cp "$OUT/vp_dlm_model.old.json" "$ROOT/vp_dlm_model.json"
python3 - "$OUT/dlm_report.json" "$fails" <<'P'
import sys, json
fn, fails = sys.argv[1], sys.argv[2].split()
r = json.load(open(fn)); r["checks"]["C"] = {"failed": fails}
if fails:
    r["ok"] = False; r["why"] = "тесты бота с новой моделью не прошли: " + ", ".join(fails)
json.dump(r, open(fn, "w"), indent=1)
print(("ПРИНЯТО: " if r["ok"] else "НЕ ПРИНЯТО: ") + r["why"])
P
echo "⚡: ${SECONDS}s"
