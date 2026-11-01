#!/bin/bash
set -e -o pipefail
cd /home/user/vp-poc-screener
python3 tools/winrate/money_2022.py deep lev | tail -6
echo "lev2022 done"
