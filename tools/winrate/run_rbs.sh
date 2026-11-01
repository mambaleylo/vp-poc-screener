#!/bin/bash
set -e -o pipefail
cd "$(dirname "$0")"
for tf in 1 2 4; do [ -f /home/user/vp-lab-store/wf/rbs_$tf.npz ] || python3 rb_short.py $tf | grep done; done
echo "rbs all done"
