#!/bin/bash
# the funding history of every lab-store coin that has none yet (for H11 new listings and the control coins)
cd "$(dirname "$0")"; set -e
ST=/home/user/vp-lab-store/data
syms=$(cd $ST/1h && for f in *.csv.gz; do s=${f%.csv.gz}; [ -f $ST/funding/$s.csv ] || echo $s; done)
echo "монет без фандинга: $(echo $syms | wc -w)"
python3 ../prv_audit/dl_fund2.py $syms | awk 'NR%50==0{print "скачано", NR; fflush()} /fund done/{print; fflush()}'
