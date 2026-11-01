#!/bin/bash
set -e -o pipefail
cd /home/user/vp-poc-screener
F="Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=17"
echo "== 2023-2025 (36 windows)"; python3 tools/winrate/money_arm2.py "$F,$F|ddc=0.3/0.5/0.15,$F|ddc=0.4/0.5/0.2,$F|ddc=0.5/0.5/0.25,$F|ddc=0.4/0.7/0.2,$F|pz=1/0.15,$F|pz=3/0.25,$F|pz=7/0.3" 1,2 4 | tail -8
echo "== 2022"; python3 tools/winrate/money_2022.py deep dd | tail -9
echo "dd all done"
