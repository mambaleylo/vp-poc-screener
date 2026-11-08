#!/bin/bash
# hypotheses 12–16 on the 210 coins, one after another (a finished one is skipped on a restart)
cd "$(dirname "$0")"; set -e
for h in 12 13 14 15 16; do
  if [ -f /home/user/flow$h.log ] && grep -q "^flow$h done" /home/user/flow$h.log; then cat /home/user/flow$h.log | grep -v "сигнал\|^  m"; continue; fi
  HYP=$h python3 flowsig.py > /home/user/flow$h.log 2>&1
  grep -v "сигнал\|^  m" /home/user/flow$h.log
done
echo "flow all done"
