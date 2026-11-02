#!/bin/bash
# SMC's events rebuilt on dl.py's 2020- candles (the bot's 127 coins) -> smc_repro.py against the deployed model
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
mkdir -p lv2_20
[ -f lv2_20/.done ] || { LV_OUT=$PWD/lv2_20 LV_D1H=$PWD/../ema_model/data/1h python3 ../new_ind/lv_engine.py $(python3 -c "import json;print(' '.join(json.load(open('lv/split.json'))['bot']))"); touch lv2_20/.done; }
LVDIR=lv2_20 python3 smc_repro.py
