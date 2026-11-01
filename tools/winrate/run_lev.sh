#!/bin/bash
set -e -o pipefail
cd /home/user/vp-poc-screener
echo "== 2022"; python3 tools/winrate/money_2022.py deep lev | tail -6
echo "== 2023-2025"; python3 tools/winrate/money_deep.py lev | tail -20
echo "lev all done"
