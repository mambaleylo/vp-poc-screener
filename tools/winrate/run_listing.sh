#!/bin/bash
cd "$(dirname "$0")"; set -e
python3 listing.py 2>&1
