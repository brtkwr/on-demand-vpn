"""Start, stop or check the WireGuard VM, and point a Cloudflare DNS record at its IP."""
import hmac
import os

import functions_framework
import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession

PROJECT, ZONE, VM = os.environ["PROJECT"], os.environ["ZONE"], os.environ["VM"]
HOST, CF_ZONE = os.environ["VPN_HOST"], os.environ["CF_ZONE"]
ZONE_API = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{ZONE}"
gce = AuthorizedSession(google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])[0])


def vm_state():
    vm = gce.get(f"{ZONE_API}/instances/{VM}").json()
    configs = vm["networkInterfaces"][0].get("accessConfigs", [])
    return vm["status"], configs[0].get("natIP", "") if configs else ""


def point_dns(ip):
    api = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}/dns_records"
    auth = {"Authorization": f"Bearer {os.environ['CF_TOKEN']}"}
    record = {"type": "A", "name": HOST, "content": ip, "ttl": 60, "proxied": False}
    found = requests.get(api, headers=auth, params={"type": "A", "name": HOST}, timeout=10).json()["result"]
    if found:
        r = requests.put(f"{api}/{found[0]['id']}", headers=auth, json=record, timeout=10)
    else:
        r = requests.post(api, headers=auth, json=record, timeout=10)
    r.raise_for_status()


@functions_framework.http
def vpn(request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not hmac.compare_digest(token.encode(), os.environ["TOKEN"].encode()):
        return "forbidden\n", 403
    action = request.args.get("action", "status")
    status, ip = vm_state()
    if action == "start":
        if status == "STOPPING":
            return "still stopping, try again in a minute\n", 409
        if status == "RUNNING":
            point_dns(ip)
            return f"already running {HOST} -> {ip}\n"
        op = gce.post(f"{ZONE_API}/instances/{VM}/start").json()
        gce.post(f"{ZONE_API}/operations/{op['name']}/wait", timeout=130).raise_for_status()
        status, ip = vm_state()
        point_dns(ip)
        return f"started {HOST} -> {ip}\n"
    if action == "stop":
        if status in ("STOPPING", "TERMINATED"):
            return f"already stopped ({status})\n"
        gce.post(f"{ZONE_API}/instances/{VM}/stop").raise_for_status()  # don't wait: stopping takes about a minute
        return "stopping\n"
    return f"{status} {ip}\n"
