#!/bin/bash
# ⚡ close2h: the bot's orders scored by the research-engine models (yearly / monthly) -> the strictest money vs the lab's
cd "$(dirname "$0")"; set -e
export TFH=2 PYTHONPATH=$PWD:$PWD/../zones_model; W=/home/user/vp-lab-store/wf
for v in Y M0; do [ -f "$W/allorders_close2h_rs$v.npz" ] || python3 dlm_allorders_rs.py $v 3; done
python3 money_roll.py
