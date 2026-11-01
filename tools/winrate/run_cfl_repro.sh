#!/bin/bash
# Классика from scratch for the audit (ev3 events -> fc_red's label & walk-forward -> cfl_repro); finished steps leave markers
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
run() { local n=$1; shift; [ -f "ev3/.ok_$n" ] || { echo "шаг $n"; "$@"; mkdir -p ev3; touch "ev3/.ok_$n"; }; }
run ev3 python3 ../new_ind/ev3_engine.py
run red python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv = ['fc_red.py']; exec(open('fc_red.py').read())"
python3 cfl_repro.py
