#!/bin/bash
# the retrain schedules for ⚡ 2h (s21h2 d2 E1); each variant's scores saved (a restart skips the done ones)
cd "$(dirname "$0")"; set -e
export TFH=2 PYTHONPATH=$PWD:$PWD/../zones_model
for v in Y M12 M24 M0; do [ -f "s21h2_roll_d2_1_$v.npz" ] || python3 dlm_roll.py s21h2 d2 1 $v; done
python3 dlm_roll_cmp.py s21h2 d2 1 0.99
