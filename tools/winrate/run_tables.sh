#!/bin/bash
# the user's money tables with 🔄 Классика (v0.99.776): a year by the start month, with the top-ups, the month's $ by the balance
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr
run() { local n=$1; shift; [ -f "/home/user/tables/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/tables/.ok_$n"; }; }
mkdir -p /home/user/tables
run months python3 money_months.py 4
run dep python3 money_dep_months.py 4
run usd python3 money_month_usd.py 2
echo "tables done"
