#!/bin/bash
# ⚡ 2h from scratch: the restored engine -> the daily features -> the deployed recipe vs the bot's trees (markers: a restart goes on)
cd "$(dirname "$0")"; set -e
export TFH=2 PYTHONPATH=$PWD:$PWD/../zones_model
run() { local n=$1; shift; [ -f "s21h2_mk/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "s21h2_mk/.ok_$n"; }; }
mkdir -p s21h2 s21h2_mk
run eng python3 s21h2_engine.py
run f2 python3 s24_featall.py s21h2
python3 s21h2_repro.py
