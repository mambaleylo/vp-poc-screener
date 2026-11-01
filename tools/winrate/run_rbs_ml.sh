#!/bin/bash
set -e -o pipefail
cd "$(dirname "$0")"
S=/home/user/vp-lab-store/wf
for tf in 1 2 4; do [ -f $S/rbs_$tf.npz ] || python3 rb_short.py $tf 2>/dev/null | grep done; done
for tf in 1 2 4; do [ -f $S/rbs_${tf}_X.npz ] && [ $S/rbs_${tf}_X.npz -nt $S/rbs_$tf.npz ] || python3 rbs_feat.py $tf 2>/dev/null | grep done; done
python3 rbs_ml.py
