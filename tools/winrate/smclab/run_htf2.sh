#!/bin/bash
# HTF: the deployed models' reproduction on the clean events, then the rule variants
cd "$(dirname "$0")"; set -e
R=/home/user/vp-poc-screener/tools
export PYTHONPATH=$R/winrate:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation
export LV_D1H=/home/user/ema211/data/1h
run() { local n=$1; shift; [ -f ".ok_$n" ] || { echo "шаг $n"; "$@"; touch ".ok_$n"; }; }
run htfrepro python3 $R/winrate/htf_repro.py
run htfvar python3 $R/winrate/htf_var.py
echo "htf2 done"
