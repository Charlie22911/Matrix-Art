#!/usr/bin/env bash
set -euo pipefail
CORE="${1:-3}"
echo "== Kernel cmdline =="
cat /proc/cmdline || true
echo
for key in isolcpus nohz_full rcu_nocbs irqaffinity; do
  if grep -qw "${key}=[^ ]*${CORE}" /proc/cmdline 2>/dev/null || [[ "$key" == "irqaffinity" && $(grep -o "irqaffinity=[^ ]*" /proc/cmdline || true) ]]; then
    echo "${key}: present"
  else
    echo "${key}: missing or not obviously targeting core ${CORE}"
  fi
done

echo
echo "== Matrix-Art process threads =="
pid="$(pgrep -f 'python3 -m matrix_art|python -m matrix_art' | head -n 1 || true)"
if [[ -n "$pid" ]]; then
  ps -L -o pid,tid,cls,rtprio,psr,pcpu,comm -p "$pid"
  echo
  echo "Process CPU affinity: $(taskset -pc "$pid" 2>/dev/null || true)"
else
  echo "Matrix-Art process not found."
fi

echo
echo "== Audio PWM conflict check =="
if lsmod | grep -q '^snd_bcm2835'; then
  echo "snd_bcm2835 is loaded. This can conflict with hardware PWM on the matrix path."
else
  echo "snd_bcm2835 is not loaded."
fi
