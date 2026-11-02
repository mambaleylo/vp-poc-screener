#!/bin/bash
cd "$(dirname "$0")"; set -e
R=/home/user/vp-poc-screener/tools
export PYTHONPATH=$R/winrate:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation
export LV_D1H=/home/user/ema211/data/1h   # the candles the events were built on (bar indices j)
run() { local n=$1; shift; [ -f ".ok_$n" ] || { echo "шаг $n"; "$@"; touch ".ok_$n"; }; }
run sct0 python3 $R/winrate/smc_sc_t0.py
run var python3 $R/winrate/smc_var.py
echo "smc2 done"
