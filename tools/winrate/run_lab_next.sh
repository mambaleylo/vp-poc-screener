#!/bin/bash
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model
python3 money_2026.py
[ -f /home/user/vp-lab-store/wf/vp_dlm_model_lab.json ] || NS=10 python3 dlm_lab_export.py
echo "lab next done"
