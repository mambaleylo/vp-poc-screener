#!/bin/bash
cd "$(dirname "$0")"; set -e
echo "== только лонги после пролива"; CASC_SIDES=1 python3 cascade.py 2>/dev/null
echo "== только шорты после сквиза"; CASC_SIDES=-1 python3 cascade.py 2>/dev/null
echo "cascade sides done"
