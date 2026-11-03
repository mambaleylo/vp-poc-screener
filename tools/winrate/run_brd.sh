#!/bin/bash
# ⚡ with the market-breadth features vs the same recipe without them (the drawdown round): the yearly walk-forward orders of
# the 4h and the shifted 4h streams, each twice (OUTSUF _b0 = no breadth, _brd = + 6 breadth features); the 2h stream as deployed
cd "$(dirname "$0")"; set -e
run() { local n=$1; shift; [ -f "/home/user/brd/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/brd/.ok_$n"; }; }
mkdir -p /home/user/brd
run w4b0 env STREAMS=wick4h OUTSUF=_b0 python3 dlm_allorders.py 3
run w4brd env STREAMS=wick4h OUTSUF=_brd BRD=1 python3 dlm_allorders.py 3
run o2b0 env STREAMS=wick4h_o2 OUTSUF=_b0 python3 dlm_allorders.py 3
run o2brd env STREAMS=wick4h_o2 OUTSUF=_brd BRD=1 python3 dlm_allorders.py 3
echo "brd done"
