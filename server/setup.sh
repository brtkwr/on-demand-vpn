#!/usr/bin/env bash
# Run as root on a fresh Debian VM: installs WireGuard, creates the server key and wg0 with NAT
# and an MSS clamp, and enables it. Leaves an existing key and config alone. Add clients with add-peer.sh.
set -euo pipefail
apt-get update && apt-get install -y wireguard iptables qrencode
cd /etc/wireguard && umask 077
[ -f server.key ] || { wg genkey > server.key; wg pubkey < server.key > server.pub; }
NIC=$(ip route show default | awk '{print $5}')

# The VPC MTU is 1460, so wg0 gets 1380. Clamping the TCP MSS to 1380 - 40 stops sites that
# ignore ICMP "fragmentation needed" (GitHub, in testing) from hanging on large packets.
[ -f wg0.conf ] || cat > wg0.conf <<CONF
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = $(cat server.key)
PostUp = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o $NIC -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o $NIC -j MASQUERADE
PostUp = iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1340
PostDown = iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1340
CONF

echo net.ipv4.ip_forward=1 > /etc/sysctl.d/99-wg.conf && sysctl --system >/dev/null
systemctl enable --now wg-quick@wg0
wg show wg0
