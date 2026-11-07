#!/bin/bash
# Классика round 3: the stop x take grid, the trail, the half, the hold, more trades — on top of the deployed A (the drought 14 d, 210 coins)
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr
run() { local n=$1; shift; [ -f "/home/user/cfl3/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/cfl3/.ok_$n"; }; }
mkdir -p /home/user/cfl3
B=c210
N=""
for sk in 0.5 0.75 1.0 1.25; do for tk in 3 4 5 6 8; do N="$N dr14+$B+s${sk}t${tk}"; done; done
for v in hd15 hd3 tr2 tr3 tr2n half2 ctf12 hold48 hold120 hold168; do N="$N dr14+$B+$v"; done
N="$N dr7+$B dr10+$B dr14_985+$B dr14+$B+q995 dr14+$B+cap30 dr14+$B+shortsq"
run var env NAMES="$N" bash ./run_cflvar.sh
echo "cfl3 done"
