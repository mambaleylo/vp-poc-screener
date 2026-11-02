#!/bin/bash
# ⚡ a third stream on another chart: the bot's features of the new charts' orders (210 coins, 4 parts at once) -> the lab's
# yearly walk-forward and every order -> the strictest money vs the bot as it is (markers: a restart goes on)
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model STREAMS=wick4h_o2,wick3h,wick6h,wick8h BASE_ONLY=1; W=/home/user/vp-lab-store/wf
mkdir -p tf_mk
if [ ! -f tf_mk/.ok_build ]; then
  echo "шаг build"; for w in 0 1 2 3; do python3 dlm_build.py $w 4 & done; wait; touch tf_mk/.ok_build
fi
[ -f tf_mk/.ok_all ] || { echo "шаг allorders"; python3 dlm_allorders.py 3; touch tf_mk/.ok_all; }
ALLSUF=_clr python3 money_tf.py
