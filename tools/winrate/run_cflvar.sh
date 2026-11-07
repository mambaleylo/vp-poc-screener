#!/bin/bash
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv = ['cfl_var.py'] + __import__('os').environ.get('NAMES', '').split(); exec(open('cfl_var.py').read())"
