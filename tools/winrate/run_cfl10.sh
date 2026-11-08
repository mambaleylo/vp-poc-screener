#!/bin/bash
# Классика round 10: the best (the 3 filters + q 0.995) with the stop 0.4 x take 8R, the room 35 / 45%
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/cfl10/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/cfl10/.ok_$n"; }; }
mkdir -p /home/user/cfl10
run lists env NAMES="dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50 dr14+c210+cap30+s0.5t6+ctf4+cap40+q995+fpos90+fatrh+fde50 dr14+c210+cap30+s0.5t6+ctf4+cap40+s0.4t8+q995+fpos90+fatrh+fde50" bash ./run_cflvar.sh
run money python3 money_cfl.py 6 3 dr14+c210+cap30+s0.5t6+ctf4@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+q995+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+cap40+q995+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+cap40+s0.4t8+q995+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+q995+fpos90+fatrh+fde50@2#0.45 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45
echo "cfl10 done"
