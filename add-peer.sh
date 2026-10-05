#!/usr/bin/env bash
# Add a client device: generates its key here, gives the VM only the public half,
# and writes <name>.conf (plus <name>.png QR code if qrencode is installed). The VM must be running.
#   ./add-peer.sh iphone 10.8.0.3
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/env.sh"
NAME=${1:?usage: $0 <name> <10.8.0.x>}; ADDR=${2:?usage: $0 <name> <10.8.0.x>}
umask 077
PRIV=$(wg genkey); PUB=$(wg pubkey <<<"$PRIV")

SERVER_PUB=$(gcloud compute ssh "$VM" --zone "$ZONE" "${GCLOUD[@]}" --command "
  sudo wg set wg0 peer $PUB allowed-ips $ADDR/32 &&
  printf '\n[Peer]\nPublicKey = $PUB\nAllowedIPs = $ADDR/32\n' | sudo tee -a /etc/wireguard/wg0.conf >/dev/null &&
  sudo cat /etc/wireguard/server.pub")

cat > "$ROOT/$NAME.conf" <<CONF
[Interface]
PrivateKey = $PRIV
Address = $ADDR/32
DNS = 1.1.1.1
MTU = 1380

[Peer]
PublicKey = $SERVER_PUB
Endpoint = $VPN_HOST:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
CONF
echo "wrote $ROOT/$NAME.conf"
if command -v qrencode >/dev/null; then qrencode -o "$ROOT/$NAME.png" < "$ROOT/$NAME.conf" && echo "wrote $ROOT/$NAME.png"; fi
echo "delete both once imported: they hold the device's private key"
