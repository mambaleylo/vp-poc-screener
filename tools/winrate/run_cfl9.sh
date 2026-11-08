#!/bin/bash
# Классика round 9: the filters with a lower bar (more trades back), then the money of round 8 / 9's best (6 paired runs, room 35%)
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/cfl9/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/cfl9/.ok_$n"; }; }
mkdir -p /home/user/cfl9
run lists env NAMES=" dr14+c210+cap30+s0.5t6+ctf4+q995+fpos90+fatrh+fde50 dr14+c210+cap30+s0.5t6+ctf4+q99+fpos90+fatrh+fde50 dr14+c210+cap30+s0.5t6+ctf4+q995+fdow+fema+fb7d dr14+c210+cap30+s0.5t6+ctf4+q995+fpos90+fatrh dr14+c210+cap30+s0.5t6+ctf4+q99+fpos90+fatrh" bash ./run_cflvar.sh
run money python3 money_cfl.py 6 3 dr14+c210+cap30+s0.5t6+ctf4@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fdow@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fb7d@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fema@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fatrh@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fpos90@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+q995+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+q99+fpos90+fatrh+fde50@2#0.35 dr14+c210+cap30+s0.5t6+ctf4+q995+fdow+fema+fb7d@2#0.35
echo "cfl9 done"
