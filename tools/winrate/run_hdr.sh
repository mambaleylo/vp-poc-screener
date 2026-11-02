#!/bin/bash
# the header for ⚡ 4h = the lab's model, 2h = the deployed (its research-engine rebuild): money_expect4.py on the _clr orders
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model
ALLSUF=_clr python3 money_expect4.py "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"
echo "hdr done"
