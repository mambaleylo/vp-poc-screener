#!/bin/bash
# Классика round 8: cfl_filt.py's filters on v0.99.777's rule, alone and together
cd "$(dirname "$0")"; set -e
NAMES=" dr14+c210+cap30+s0.5t6+ctf4+fpos90 dr14+c210+cap30+s0.5t6+ctf4+fatrh dr14+c210+cap30+s0.5t6+ctf4+fde50 dr14+c210+cap30+s0.5t6+ctf4+fpos365 dr14+c210+cap30+s0.5t6+ctf4+fdatr dr14+c210+cap30+s0.5t6+ctf4+fb7d dr14+c210+cap30+s0.5t6+ctf4+fdow dr14+c210+cap30+s0.5t6+ctf4+fema dr14+c210+cap30+s0.5t6+ctf4+fpos90+fatrh dr14+c210+cap30+s0.5t6+ctf4+fpos90+fatrh+fde50 dr14+c210+cap30+s0.5t6+ctf4+fpos90+fatrh+fde50+fdatr dr14+c210+cap30+s0.5t6+ctf4+fpos90+fatrh+fde50+fpos365+fdatr+fb7d dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+fpos90+fatrh dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+fpos90+fatrh+fde50" bash ./run_cflvar.sh
echo "cfl8 done"
