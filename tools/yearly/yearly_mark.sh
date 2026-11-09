#!/bin/bash
# the yearly retrain's marks on the branch yearly-status (status.json): started | prepared | fallback — the main way (the claude.ai
# task in the chat) writes "started" first and "prepared" when the new models wait for the user's «да»; the GitHub fallback
# writes "fallback". yearly_gate.py reads them. usage: yearly_mark.sh started|prepared|fallback [year]
set -e
KIND=$1; YEAR=${2:-$(date -u +%Y)}; NOW=$(date -u +%s)
REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
URL=$(git -C "$REPO" remote get-url origin)
T=$(mktemp -d)
if git clone -q --depth 1 -b yearly-status "$URL" "$T/s" 2>/dev/null; then :; else
  git init -q "$T/s"; git -C "$T/s" checkout -q --orphan yearly-status; git -C "$T/s" remote add origin "$URL"
fi
cd "$T/s"
python3 - "$KIND" "$YEAR" "$NOW" <<'P'
import sys, json, os
k, y, now = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
st = json.load(open("status.json")) if os.path.exists("status.json") else {}
if st.get("year") != y:
    st = {"year": y}
st[k] = now
json.dump(st, open("status.json", "w"), indent=1)
open("README.md", "w").write("Отметки годового переобучения (tools/yearly/yearly_mark.sh, читает yearly_gate.py). Не бот, не данные.\n")
print(st)
P
git add status.json README.md
git -c user.name="${GIT_NAME:-yearly}" -c user.email="${GIT_EMAIL:-yearly@users.noreply.github.com}" commit -q -m "yearly-status: $KIND $YEAR" || true
for i in 1 2 3 4; do git push -q origin HEAD:yearly-status && break; sleep $((2 ** i)); done
rm -rf "$T"
