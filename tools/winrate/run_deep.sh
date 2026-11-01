#!/bin/bash
set -e
cd /home/user/vp-poc-screener
echo "== 2022"; python3 tools/winrate/money_2022.py deep | tail -6
echo "== 2023-2025"; python3 tools/winrate/money_deep.py | tail -20
echo "deep all done"
