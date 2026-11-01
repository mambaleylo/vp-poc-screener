#!/bin/bash
set -e -o pipefail
cd /home/user/vp-poc-screener
[ -f /home/user/vp-lab-store/wf/allorders_close2h_newc.npz ] || COINS=new OUTSUF=_newc python3 tools/winrate/dlm_allorders.py 3
B="Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=17"
echo "== the bot's coins"; python3 tools/winrate/money_arm2.py "$B" 1,2 4 | tail -1
echo "== + the new coins' ⚡"; PLUSNEW=1 python3 tools/winrate/money_arm2.py "$B" 1,2 4 | tail -1
echo "newdlm done"
