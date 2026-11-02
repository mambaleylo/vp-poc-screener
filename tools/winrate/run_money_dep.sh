#!/bin/bash
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model
[ -f /home/user/vp-lab-store/wf/allorders_close2h_dep.npz ] || python3 dlm_allorders_dep.py
python3 money_4h.py
