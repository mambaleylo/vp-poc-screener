#!/bin/bash
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model
[ -f /home/user/vp-lab-store/wf/allorders_wick4h_rsY.npz ] && [ ! -L /home/user/vp-lab-store/wf/allorders_wick4h_rsY.npz ] || STREAM=wick4h python3 dlm_allorders_rs.py Y 3
python3 money_4h.py
