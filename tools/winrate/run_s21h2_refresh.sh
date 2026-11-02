#!/bin/bash
# ⚡ 2h refresh check: the restored engine on the 2020-..October candles -> the daily features -> the deployed recipe's parity
# -> the mid-year refresh vs the deployed trees out of sample (s21h2_refresh.py) (markers: a restart goes on)
cd "$(dirname "$0")"; set -e
export TFH=2 PYTHONPATH=$PWD:$PWD/../zones_model
run() { local n=$1; shift; [ -f "s21h2_mk/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "s21h2_mk/.ok_$n"; }; }
mkdir -p s21h2 s21h2_mk
run eng python3 s21h2_engine.py
run f2 python3 s24_featall.py s21h2
run repro python3 s21h2_repro.py
python3 s21h2_refresh.py "$@"
