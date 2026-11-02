#!/bin/bash
# the EMA lab from scratch (for the improvement round): the touches -> the table -> the far-take labels -> the fill depth ->
# the yearly walk-forward scores of the deployed label (er_sc_F_0.75_4.0_3.npz, ema_h.py's input); markers: a restart goes on.
# NB: er/ and er3/ cache each coin (er_build, er_lab3): a coin whose candles changed -> delete its er/ and er3/ .pkl first
cd "$(dirname "$0")"; set -e
mkdir -p data
run() { local n=$1; shift; [ -f "data/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "data/.ok_$n"; }; }
run build python3 er_build.py
run df python3 er_df.py
run lab3 python3 er_lab3.py
run pen python3 er_pen.py
run final python3 er_final.py F_0.75_4.0_3   # the yearly walk-forward scores er_sc_<LAB>.npz (er_wf.py saves none)
echo "ema lab done"
