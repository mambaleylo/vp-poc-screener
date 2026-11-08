#!/bin/bash
# Классика's quiet — the rules without a model (cfl_idle3.py), then the bundle's money (6 paired runs, the room 45%): Классика alone vs + each rule
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/idle3/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/idle3/.ok_$n"; }; }
mkdir -p /home/user/idle3
run lists bash ./run_cfl_idle.sh cfl_idle3.py
run money python3 money_cfl.py 6 3 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50+idleK@2#0.45 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50+idleKS@2#0.45 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50+idleKSN@2#0.45
echo "idle3 done"
