#!/bin/bash
# the lab's long jobs under a watchdog (the user: "не сигнал, а исправление и дальнейшее продолжение процесса"): every
# minute — done (DONE_RE in the log) -> exit 0; the job gone without it -> restarted (up to TRIES); its CPU time not
# growing for STALL minutes -> killed and restarted; each event one line (the watcher's notification).
# usage: supervise.sh LOG DONE_RE MATCH CMD...   (MATCH: the job's own "python3 <script>" — an existing run is adopted)
LOG=$1; DONE=$2; MATCH=$3; shift 3; TRIES=${TRIES:-3}; STALL=${STALL:-3}
cpu() { ps -eo times,args | awk -v m="$MATCH" 'index($0, m) && $2=="python3" {s+=$1} END {print s+0}'; }
alive() { ps -eo args | awk -v m="$MATCH" 'index($0, m) == 1' | wc -l; }
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
