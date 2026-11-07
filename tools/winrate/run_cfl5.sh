#!/bin/bash
# Классика round 5 (v0.99.776 -> the combination): the stop 0.5 dATR x take 6/8R + the stop at the 4h close + cap 30, on the own room 35/45%
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
A=dr14+c210+cap30
[ -f /home/user/vp-lab-store/wf/cfl_var_$A+s0.5t8+ctf4.json ] || NAMES="$A+s0.5t8+ctf4" bash ./run_cflvar.sh
python3 money_cfl.py 6 3 none dr14+c210@2#0.25 $A+s0.5t6@2#0.35 $A+s0.5t6+ctf4@2#0.35 $A+s0.5t8+ctf4@2#0.35 $A+s0.5t6+ctf4@2#0.45 $A+s0.5t6+ctf4@2.5#0.35 dr14+c210@2#0.35
echo "cfl5 done"
