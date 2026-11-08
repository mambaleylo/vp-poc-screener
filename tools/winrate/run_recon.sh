#!/bin/bash
# HANDOFF 2a: the header rule vs the top-ups tool on the same starts
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
python3 recon_hdr.py 4 2>&1
