#!/bin/bash
# P/R's monthly retrain (RETRAIN.md) to the end of last month: the funding's missing months, the events on the candles to the
# month's end (tools/ema_model/data/1h, 127 coins), the deployed model reproduced, then prv_month.py. Resumable steps.
cd "$(dirname "$0")"; set -e -o pipefail
END=${END:-$(date -u -d "$(date -u +%Y-%m-01) -1 day" +%Y-%m)}
export LABSTORE=/home/user/vp-lab-store PRV_OUT=/home/user/prv_month PRV_C1H=$PWD/../ema_model/data/1h FUND_END=$END
export PYTHONPATH=$PWD:$PWD/../neuro_model:$PWD/../winrate
mkdir -p $PRV_OUT; run() { local n=$1; shift; [ -f "$PRV_OUT/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "$PRV_OUT/.ok_$n"; }; }
run fund python3 dl_fund2.py
run ev python3 prv_ev2.py
run repro env LABSTORE=$PRV_OUT python3 prv_repro.py
run month python3 ../adaptation/prv_month.py
echo "prv month chain done"
