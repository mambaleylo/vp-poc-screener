#!/bin/bash
# the SMC lab from scratch on the clean 2020- candles (fill_gaps): the levels' events of the 127 bot coins + the 83 check coins
# -> the yearly walk-forward scores (trained on the 127 only, lv_wf.scores) -> the deployed model's reproduction
cd "$(dirname "$0")"; set -e
R=/home/user/vp-poc-screener/tools
export PYTHONPATH=$R/winrate:$R/new_ind:$R/zones_model:$R/neuro_model:$R/adaptation
run() { local n=$1; shift; [ -f ".ok_$n" ] || { echo "шаг $n"; "$@"; touch ".ok_$n"; }; }
run lv env LV_OUT=$PWD/lv2 LV_D1H=/home/user/ema211/data/1h python3 $R/new_ind/lv_engine.py $(python3 -c "import json;s=json.load(open('lv/split.json'));print(' '.join(s['bot']+s['chk']))")
run sc python3 sc.py
run repro env LVDIR=lv2 python3 $R/winrate/smc_repro.py
echo "smc lab done"
