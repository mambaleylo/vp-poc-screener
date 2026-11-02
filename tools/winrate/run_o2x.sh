#!/bin/bash
# improving the shifted 4h stream: the o1 / o3 grids, o2 at q0.98, o2 by one model on both 4h grids -> money_o2 (markers)
cd "$(dirname "$0")"; set -e
export PYTHONPATH=$PWD:$PWD/../zones_model BASE_ONLY=1; W=/home/user/vp-lab-store/wf
mkdir -p tf_mk
if [ ! -f tf_mk/.ok_build13 ]; then
  echo "шаг build o1 o3"; for w in 0 1 2 3; do STREAMS=wick4h_o1,wick4h_o3 python3 dlm_build.py $w 4 & done; wait; touch tf_mk/.ok_build13
fi
[ -f tf_mk/.ok_all13 ] || { echo "шаг allorders o1 o3"; STREAMS=wick4h_o1,wick4h_o3 python3 dlm_allorders.py 3; touch tf_mk/.ok_all13; }
[ -f tf_mk/.ok_q98 ] || { echo "шаг o2 q0.98"; STREAMS=wick4h_o2 python3 dlm_allorders.py 3 0.98; touch tf_mk/.ok_q98; }
[ -f tf_mk/.ok_mix ] || { echo "шаг o2 общая модель"; STREAMS=wick4h_o2 TRAIN_STREAMS=wick4h,wick4h_o2 OUTSUF=_mix python3 dlm_allorders.py 3; touch tf_mk/.ok_mix; }
ALLSUF=_clr python3 money_o2.py 6
