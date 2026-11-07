#!/bin/bash
# Классика round 2 (after v0.99.776): the variants on top of the deployed A (dr14+c210), then the bundle's money
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr
run() { local n=$1; shift; [ -f "/home/user/cfl2/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/cfl2/.ok_$n"; }; }
mkdir -p /home/user/cfl2
A=dr14+c210
run var env NAMES="$A $A+be2 $A+be1 $A+part1 $A+take3 $A+take5 $A+take6 $A+hold72 $A+hold144 $A+ctf4 $A+stop1 $A+stop05 $A+hard3 $A+lim025 $A+lim05 $A+only4h $A+only1d $A+cap10 $A+cap30" bash ./run_cflvar.sh
run money python3 money_cfl.py 4 3 none $A@2#0.25 $A@1.5#0.25 $A@2.5#0.25 $A@3#0.25 $A@2#0.15 $A@2#0.35 $A+be2@2#0.25 $A+part1@2#0.25 $A+take3@2#0.25 $A+take5@2#0.25 $A+hold144@2#0.25 $A+ctf4@2#0.25 $A+lim025@2#0.25 $A+only4h@2#0.25 $A+cap30@2#0.25
echo "cfl2 done"
