#!/bin/bash
# every module's retrain schedules (roll_mod.py), the done ones skipped; then the table
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../prv_audit
# ⚡ 4h first: the research events (s23_engine, the deployed w1 / E0) -> the daily features -> dlm_roll's schedules
mkdir -p s23_mk
[ -f s23_mk/.ok_eng ] || { TFH=4 COINS=coins127.txt python3 s23_engine.py; touch s23_mk/.ok_eng; }
[ -f s23_mk/.ok_f2 ] || { TFH=4 python3 s24_featall.py s23_4h; touch s23_mk/.ok_f2; }
for v in Y M12 M24 M0; do [ -f "s23_4h_roll_w1_0_$v.npz" ] || TFH=4 python3 dlm_roll.py s23_4h w1 0 $v; done
TFH=4 python3 dlm_roll_cmp.py s23_4h w1 0 0.99
for mod in prv rbs smc htf cfl ema; do
  for v in Y Q M0 M12 M24; do [ -f "roll_${mod}_$v.npz" ] || python3 roll_mod.py $mod $v; done
  [ $mod = prv ] && { [ -f roll_prv_Q24.npz ] || python3 roll_mod.py prv Q24; }
  python3 roll_mod_cmp.py $mod
done
echo "roll all done"
