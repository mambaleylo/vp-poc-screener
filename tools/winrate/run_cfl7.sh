#!/bin/bash
# Классика round 7: round 6's best together (cap 50 / 40, the stop 0.4 x take 8 / the take 7, the drought's bar 0.98, the shorts, 4h only)
cd "$(dirname "$0")"; set -e
NAMES=" dr14+c210+cap30+s0.5t6+ctf4+cap50+s0.4t8 dr14+c210+cap30+s0.5t6+ctf4+cap50+s0.5t7 dr14+c210+cap30+s0.5t6+ctf4+cap40+s0.4t8 dr14+c210+cap30+s0.5t6+ctf4+cap50+dr14_98 dr14+c210+cap30+s0.5t6+ctf4+cap50+both dr14+c210+cap30+s0.5t6+ctf4+cap50+s0.4t8+dr14_98 dr14+c210+cap30+s0.5t6+ctf4+cap50+s0.5t7+dr14_98 dr14+c210+cap30+s0.5t6+ctf4+cap50+both+dr14_98 dr14+c210+cap30+s0.5t6+ctf4+cap50+only4h dr14+c210+cap30+s0.5t6+ctf4+cap50+s0.4t8+only4h" bash ./run_cflvar.sh
echo "cfl7 done"
