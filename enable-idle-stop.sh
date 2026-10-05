#!/usr/bin/env bash
# Install the idle auto-stop on the VM (must be running): copies server/idle-stop.sh, gives
# the VM the function URL and token (root-only), and runs it every 5 minutes.
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/env.sh"
gcloud compute scp "$ROOT/server/idle-stop.sh" "$VM":/tmp/idle-stop.sh --zone "$ZONE" "${GCLOUD[@]}"
{ echo "$FUNCTION_URL"; gcloud secrets versions access latest --secret vpn-switch-token "${GCLOUD[@]}"; echo; } |
  gcloud compute ssh "$VM" --zone "$ZONE" "${GCLOUD[@]}" --command 'sudo bash -c "
set -e; umask 077
read -r url; read -r token
printf %s \"\$url\" > /etc/wireguard/vpn-switch.url
printf %s \"\$token\" > /etc/wireguard/vpn-switch.token
install -m 755 /tmp/idle-stop.sh /usr/local/sbin/idle-stop
cat > /etc/systemd/system/idle-stop.service <<UNIT
[Unit]
Description=Stop the VM when no WireGuard client is connected
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/idle-stop
UNIT
cat > /etc/systemd/system/idle-stop.timer <<UNIT
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload && systemctl enable --now idle-stop.timer
DRY_RUN=1 /usr/local/sbin/idle-stop"'
