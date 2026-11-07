#!/bin/bash
# v0.99.778 — Классика's audit: the market fills of a profitable time exit counted (all modules) -> the old vs the new rule
# again, the header, the user's tables (resumable steps)
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/a778/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/a778/.ok_$n"; }; }
mkdir -p /home/user/a778
run cmp python3 money_cfl.py 6 3 none dr14+c210@2#0.25 dr14+c210+cap30+s0.5t6+ctf4@2#0.35
run hdr python3 money_hdr2.py 4
run months python3 money_months.py 4
run dep python3 money_dep_months.py 4
run usd python3 money_month_usd.py 2
echo "audit778 done"
