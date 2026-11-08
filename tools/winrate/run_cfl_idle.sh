#!/bin/bash
# Классика's quiet times: what works then (cfl_idle.py) in run_cflvar.sh's environment
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); exec(compile(open('cfl_idle.py').read(), 'cfl_idle.py', 'exec'))"
