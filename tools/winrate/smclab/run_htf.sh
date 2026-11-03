#!/bin/bash
# HTF from scratch on the SMC lab's events (lv2: fam <= 22): the two models' yearly walk-forward scores
cd "$(dirname "$0")"; set -e
R=/home/user/vp-poc-screener/tools
export PYTHONPATH=$R/winrate:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation
export LV_D1H=/home/user/ema211/data/1h
run() { local n=$1; shift; [ -f ".ok_$n" ] || { echo "шаг $n"; "$@"; touch ".ok_$n"; }; }
run htfsc python3 $R/winrate/htf_sc.py
echo "htf lab done"
