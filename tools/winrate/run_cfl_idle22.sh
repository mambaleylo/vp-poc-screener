#!/bin/bash
# Классика's quiet module with the history from 2022-07 (the 2024 model learns 2022-07 .. 2023): cfl_idle.py -> cfl_idle2.py
cd "$(dirname "$0")"; set -e
export CFL_FROM=2022-07 CFL_IDLE_TAG=_22
run() { local n=$1; shift; [ -f "/home/user/idle22/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/idle22/.ok_$n"; }; }
mkdir -p /home/user/idle22
run quiet bash ./run_cfl_idle.sh cfl_idle.py
run model bash ./run_cfl_idle.sh cfl_idle2.py
echo "idle22 done"
