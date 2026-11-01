#!/bin/bash
set -e -o pipefail
cd "$(dirname "$0")"
python3 dl_fund2.py | grep "fund done"
rm -rf /home/user/vp-lab-store/prv_ev.nofund; [ -d /home/user/vp-lab-store/prv_ev ] && [ ! -f /home/user/vp-lab-store/prv_ev/.fund ] && mv /home/user/vp-lab-store/prv_ev /home/user/vp-lab-store/prv_ev.nofund || true
mkdir -p /home/user/vp-lab-store/prv_ev && touch /home/user/vp-lab-store/prv_ev/.fund
python3 prv_ev2.py 2>/dev/null | grep "done"
echo "prv rebuild done"
