#!/bin/bash
# Классика on 100 more coins: the open interest / long-short (data.binance.vision daily metrics) and the funding, the ev3 events
# (ev3x/), their scores (cfl_more_sc.py), then the deployed rule and the filters' best on 310 coins (cfl_var.py with CFL_X / CFL_SC)
cd "$(dirname "$0")"; set -e
export LABSTORE=/home/user/vp-lab-store PYTHONPATH=$PWD:$PWD/../new_ind:$PWD/../zones_model:$PWD/../neuro_model
run() { local n=$1; shift; [ -f "cfl_more/.ok_$n" ] || { echo "шаг $n"; "$@"; mkdir -p cfl_more; touch "cfl_more/.ok_$n"; }; }
mkdir -p cfl_more data; [ -e data/metrics ] || ln -s $LABSTORE/data/metrics data/metrics; [ -e data/funding ] || ln -s $LABSTORE/data/funding data/funding
C="ASTERUSDT AKEUSDT XPLUSDT WLFIUSDT VELVETUSDT BULLAUSDT STOUSDT ESPORTSUSDT QNTUSDT USELESSUSDT UBUSDT IPUSDT PLAYUSDT BTRUSDT DUSKUSDT BLESSUSDT SAHARAUSDT ORCAUSDT ARIAUSDT BUSDT MYXUSDT EDENUSDT PIXELUSDT 0GUSDT FHEUSDT BARDUSDT LIGHTUSDT STGUSDT HEMIUSDT GUNUSDT AIOTUSDT MUSDT PHAUSDT TACUSDT RESOLVUSDT GUSDT TRADOORUSDT NAORISUSDT FIDAUSDT SIGNUSDT FFUSDT QUSDT SOONUSDT RAYSOLUSDT AIAUSDT VANRYUSDT DOGSUSDT INUSDT SOMIUSDT AGLDUSDT AVNTUSDT DEGOUSDT TAKEUSDT BASUSDT HIGHUSDT IOSTUSDT PTBUSDT SOPHUSDT INITUSDT TUSDT FLOCKUSDT JELLYJELLYUSDT CUSDT MOODENGUSDT TNSRUSDT COSUSDT ZEREBROUSDT LAYERUSDT XANUSDT VTHOUSDT TAGUSDT ZORAUSDT AIOUSDT MEUSDT DUSDT AUCTIONUSDT FORMUSDT AGTUSDT ZKCUSDT SWARMSUSDT HOLOUSDT PROVEUSDT AINUSDT AXLUSDT DRIFTUSDT DOLOUSDT TAIKOUSDT KERNELUSDT MERLUSDT NFPUSDT PARTIUSDT DENTUSDT LPTUSDT ERAUSDT HANAUSDT LINEAUSDT MEMEUSDT SUSDT API3USDT COAIUSDT"
run metrics python3 ../new_data/dl_metrics2.py $C
run funding env FUND_END=2026-09 python3 ../prv_audit/dl_fund2.py $C
run events python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); sys.argv = ['x'] + '$C'.split(); import ev3_engine as E3, multiprocessing as mp; E3.E2.OUT[0] = 'ev3x'; import os; os.makedirs('ev3x', exist_ok=True); p = mp.Pool(4); [print(s, m, flush=True) for s, m in p.imap_unordered(E3.E2.run, sys.argv[1:])]; print('ev3x done', flush=True)"
run scores python3 -c "import sys, types; sys.modules['nx_h'] = types.SimpleNamespace(pain=None); exec(compile(open('cfl_more_sc.py').read(), 'cfl_more_sc.py', 'exec'))"
B=dr14+c210+cap30+s0.5t6+ctf4; F=q995+fpos90+fatrh+fde50
run vars env CFL_X=ev3x CFL_SC=fc_red_sc_x.npz CFL_TAG=_x310 NAMES="$B $B+$F $B+s0.4t8+$F $B+s0.4t8 $B+cap50 $B+cap50+$F" bash ./run_cflvar.sh
echo "cfl more done"
