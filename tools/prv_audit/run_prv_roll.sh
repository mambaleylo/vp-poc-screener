#!/bin/bash
cd "$(dirname "$0")"; set -e
for v in Q24 M24 M0; do [ -f /home/user/vp-lab-store/wf/prv_roll_$v.json ] || python3 prv_roll.py $v; done
echo "prv roll all done"
