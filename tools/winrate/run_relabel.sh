#!/bin/bash
# the ⚡ relabel experiment end to end (under supervise.sh): labels for 1.75 / 1.2, the yearly models on them, every order
# scored, the strictest money of the new-label orders vs the current ones
set -e -o pipefail
cd /home/user/vp-poc-screener
python3 tools/winrate/dlm_relabel.py v175 1.2 1.75
[ -f /home/user/vp-lab-store/wf/allorders_close2h_v175.npz ] || FEATDIR=feat_v175 OUTSUF=_v175 python3 tools/winrate/dlm_allorders.py 3
B="Bn|arm=0.6|oth=1|dis=1.0|heat=1.0"
echo "== the current model's orders"; python3 tools/winrate/money_arm2.py "$B" 1,2 1 | tail -1
echo "== the new-label model's orders"; ALLSUF=_v175 python3 tools/winrate/money_arm2.py "$B" 1,2 1 | tail -1
echo "relabel experiment done"
