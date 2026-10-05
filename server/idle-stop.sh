#!/usr/bin/env bash
# Runs on the VM from a systemd timer: stops the VM through the switch function (which also
# parks DNS) once no client has handshaken for IDLE_MIN minutes. Connected clients handshake
# at least every 2 minutes. DRY_RUN=1 prints the decision without stopping.
set -euo pipefail
IDLE_MIN=${IDLE_MIN:-15}
limit=$((IDLE_MIN * 60)); now=$(date +%s)
uptime=$(cut -d. -f1 /proc/uptime)
last=$(wg show wg0 latest-handshakes | awk '{print $2}' | sort -n | tail -1)
idle=$((now - ${last:-0})); [ "${last:-0}" -eq 0 ] && idle=$uptime  # no handshake since boot

if [ "$uptime" -lt "$limit" ] || [ "$idle" -lt "$limit" ]; then
  [ -n "${DRY_RUN:-}" ] && echo "keep: idle ${idle}s, uptime ${uptime}s, limit ${limit}s"
  exit 0
fi
echo "idle ${idle}s >= ${limit}s, stopping"
[ -n "${DRY_RUN:-}" ] && exit 0
url=$(cat /etc/wireguard/vpn-switch.url)
printf 'Authorization: Bearer %s\n' "$(cat /etc/wireguard/vpn-switch.token)" |
  curl -sS --fail-with-body --max-time 30 -H @- "$url?action=stop" || poweroff  # still stop if the call fails
