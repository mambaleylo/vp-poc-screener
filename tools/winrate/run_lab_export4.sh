#!/bin/bash
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model
LABEL=feat STREAMS=wick4h SUF=_4h NS=10 python3 dlm_lab_export.py
