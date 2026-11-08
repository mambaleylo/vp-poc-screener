#!/bin/bash
# Классика's unused room lent to the bundle (money_arm2 cflgive=q: in its quiet; =a: whenever none of its trades is open): the
# whole history (every 3rd week) and the windows from 2025 only
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/give/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/give/.ok_$n"; }; }
mkdir -p /home/user/give
run all env MC_TAG=_give python3 money_cfl.py 6 3 "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45" "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45%cflgive=q" "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45%cflgive=a"
run oos env MC_FROM=2025-01 MC_TAG=_give_oos python3 money_cfl.py 6 1 "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45" "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45%cflgive=q" "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50@2#0.45%cflgive=a"
echo "give all done"
