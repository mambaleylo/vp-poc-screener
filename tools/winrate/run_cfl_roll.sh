#!/bin/bash
# Классика's retrain schedule re-checked on the rule of v0.99.776 (the drought 14 d, 210 coins): roll_mod.py's out-of-sample
# scores (Y: all history once a year — as now, Q: every 3 months, M24: the last 24 months every month) -> the deployed rule's
# list per schedule -> the bundle's money (2% on its own 25% room)
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/cflroll/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/cflroll/.ok_$n"; }; }
mkdir -p /home/user/cflroll
for v in Y Q M24; do
  run sc$v python3 roll_mod.py cfl $v
  run var$v env CFL_SC=roll_cfl_$v.npz CFL_TAG=_$v NAMES="dr14+c210" bash ./run_cflvar.sh
done
run money python3 money_cfl.py 4 2 none dr14+c210_Y@2#0.25 dr14+c210_Q@2#0.25 dr14+c210_M24@2#0.25
echo "cfl roll done"
