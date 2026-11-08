#!/bin/bash
# v0.99.781: the bot vs the backtest (t_cfl_bot.py) and the header re-counted (money_hdr2.py) on the new Классика list
cd "$(dirname "$0")"; set -e
export ALLSUF=_clr PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model:$PWD/../adaptation
run() { local n=$1; shift; [ -f "/home/user/a781/.ok_$n" ] || { echo "шаг $n"; "$@"; touch "/home/user/a781/.ok_$n"; }; }
mkdir -p /home/user/a781
run bot python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv=['t_cfl_bot.py']; exec(compile(open('t_cfl_bot.py').read(), 't_cfl_bot.py', 'exec'), {'__file__': '$PWD/t_cfl_bot.py', '__name__': '__main__'})"
run hdr python3 money_hdr2.py 4
echo "audit781 done"
