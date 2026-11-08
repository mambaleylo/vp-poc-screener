#!/bin/bash
# ⚡ alone: a year from $200 + 5 x $100 by the start month (the first month with +$2000)
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr GOAL=2000 DEP_S0=200 DEP_N=5 DEP_ONLY_DLM=1 PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
python3 money_dep_months.py 4
