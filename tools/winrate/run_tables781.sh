#!/bin/bash
# the user's tables with v0.99.781's Классика: a year from $200 + 5 x $100 by the start month (the first month with +$2000),
# and the month's $ by the balance (the share of months with +$2000)
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr GOAL=2000 PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/t781/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/t781/.ok_$n"; }; }
mkdir -p /home/user/t781
run dep env DEP_S0=200 DEP_N=5 python3 money_dep_months.py 4
run usd python3 money_month_usd.py 2
echo "tables781 done"
