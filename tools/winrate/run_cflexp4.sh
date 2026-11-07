#!/bin/bash
# v0.99.777: Классика's backtest list and model rule (cfl_export4.py)
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); exec(open('cfl_export4.py').read())"
echo "cfl export4 done"
