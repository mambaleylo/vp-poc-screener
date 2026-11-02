#!/bin/bash
# HTF's schedules again with the label on the lab-store's candles (htf_repro_rl.load_ls)
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../prv_audit
for v in Y Q M0 M12 M24; do [ -f "roll_htf_$v.npz" ] || python3 roll_mod.py htf $v; done
python3 roll_mod_cmp.py htf
