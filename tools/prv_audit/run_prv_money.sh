#!/bin/bash
cd "$(dirname "$0")"; set -e
for v in Q24 M24; do [ -f /home/user/vp-lab-store/wf/prv_roll_${v}_sc.npz ] || python3 prv_roll.py $v; done
python3 prv_money.py Q24 M24
