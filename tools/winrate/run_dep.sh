#!/bin/bash
# the header's money with top-ups (the user: +$100 a month for the first half-year): the _clr orders (⚡ 4h = the lab's
# model, 2h = the deployed recipe on the restored engine), money_dep.py (markers: a restart goes on)
cd "$(dirname "$0")"; set -e
export TFH=2 PYTHONPATH=$PWD:$PWD/../zones_model; W=/home/user/vp-lab-store/wf
[ -f "$W/allorders_close2h_rsY.npz" ] || python3 dlm_allorders_rs.py Y 3
[ -f "$W/allorders_close2h_clr.npz" ] || cp "$W/allorders_close2h_rsY.npz" "$W/allorders_close2h_clr.npz"
[ -f "$W/allorders_wick4h_clr.npz" ] || cp "$W/allorders_wick4h.npz" "$W/allorders_wick4h_clr.npz"
ALLSUF=_clr python3 money_dep.py
