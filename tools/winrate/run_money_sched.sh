#!/bin/bash
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../prv_audit
python3 money_sched.py htf Y Q M12
python3 money_sched.py smc Y M12
echo "money sched all done"
