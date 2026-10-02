#!/bin/bash
# ExecStartPost for healthvault-ollama-gpu.service (2026-10-01).
# Even after waiting for nvidia-smi, Ollama's own GPU discovery can time out at
# boot and the server silently runs CPU-only (seen after the 2026-10-01 15:47
# reboot). This waits for the server's "inference compute" line from THIS start
# and fails if it's CPU-only, so systemd's Restart=on-failure retries the start
# (a later start has always found CUDA).
since="$(date '+%Y-%m-%d %H:%M:%S' -d '-5 sec')"
for _ in $(seq 1 60); do
  line=$(journalctl --user -u healthvault-ollama-gpu --since "$since" --no-pager 2>/dev/null | grep -a 'msg="inference compute"' | tail -1)
  if [ -n "$line" ]; then
    if echo "$line" | grep -q 'library=CUDA'; then
      echo "GPU check: CUDA detected"
      exit 0
    fi
    echo "GPU check: CPU-only - failing so systemd restarts the server"
    exit 1
  fi
  sleep 2
done
echo "GPU check: no inference-compute line within 120 s - failing"
exit 1
