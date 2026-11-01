#!/bin/bash
# the lab's long jobs under a watchdog (the user: "не сигнал, а исправление и дальнейшее продолжение процесса"): every
# minute — done (DONE_RE in the log) -> exit 0; the job gone without it -> restarted (up to TRIES); its CPU time not
# growing for STALL minutes -> killed and restarted; each event one line (the watcher's notification).
# usage: supervise.sh LOG DONE_RE MATCH CMD...   (MATCH: the job's own "python3 <script>" — an existing run is adopted)
LOG=$1; DONE=$2; MATCH=$3; shift 3; TRIES=${TRIES:-3}; STALL=${STALL:-3}
roots() { ps -eo pid,args | awk -v m="$MATCH" '{p=$1; $1=""; sub(/^ /, "")} index($0, m) == 1 {print p}'; }
cpu() {   # the CPU seconds of the job and every process under it (a chain of scripts, a pool's workers)
  ps -eo pid,ppid,times | awk -v r="$(roots | tr '\n' ' ')" 'BEGIN {n = split(r, a, " "); for (i = 1; i <= n; i++) keep[a[i]] = 1}
    NR > 1 {pp[$1] = $2; t[$1] = $3} END {ch = 1; while (ch) {ch = 0; for (p in pp) if (!(p in keep) && (pp[p] in keep)) {keep[p] = 1; ch = 1}}
    for (p in keep) s += t[p]; print s + 0}'; }
alive() { roots | wc -l; }
start() { echo "запуск: $*" >> "$LOG.sup"; setsid nohup "$@" > "$LOG" 2>&1 & }
[ "$(alive)" -eq 0 ] && ! grep -qE "$DONE" "$LOG" 2>/dev/null && start "$@"
tries=0; prev=-1; idle=0; n=0
while true; do
  sleep 60
  if grep -qE "$DONE" "$LOG" 2>/dev/null; then echo "ГОТОВО"; exit 0; fi
  if [ "$(alive)" -eq 0 ]; then
    tries=$((tries+1)); err=$(tail -c 400 "$LOG" 2>/dev/null | tr '\n' ' ')
    if [ $tries -gt $TRIES ]; then echo "НЕ ВЫШЛО после $TRIES перезапусков — нужна правка: $err"; exit 1; fi
    echo "упал, перезапуск $tries/$TRIES: $err"; start "$@"; prev=-1; idle=0; continue
  fi
  t=$(cpu)
  if [ "$t" -le "$prev" ]; then idle=$((idle+1)); else idle=0; fi
  if [ $idle -ge $STALL ]; then
    tries=$((tries+1)); pkill -f "^python3 ${MATCH#python3 }" ; sleep 3
    if [ $tries -gt $TRIES ]; then echo "ЗАВИСАЕТ после $TRIES перезапусков — нужна правка"; exit 1; fi
    echo "завис ($STALL мин без счёта), перезапуск $tries/$TRIES"; start "$@"; prev=-1; idle=0; continue
  fi
  prev=$t; n=$((n+1)); [ $((n % 10)) -eq 0 ] && echo "идёт: ${t}с процессора"
done
