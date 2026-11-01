#!/bin/bash
# the EMA chain from scratch for the audit; every finished step leaves a marker (a restart goes on from there)
cd "$(dirname "$0")"; set -e
mkdir -p data
run() { local n=$1; shift; [ -f "data/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "data/.ok_$n"; }; }
run dl python3 ../zones_model/dl.py 1h
run build python3 er_build.py
run df python3 er_df.py
run lab3 python3 er_lab3.py
run pen python3 er_pen.py
python3 ema_repro.py
