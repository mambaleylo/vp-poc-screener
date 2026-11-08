#!/bin/bash
# Классика's quiet times (cfl_idle.py: what works then; cfl_idle2.py: a model of its own) in run_cflvar.sh's environment
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
S=${1:-cfl_idle.py}
python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); exec(compile(open('$S').read(), '$S', 'exec'))"
