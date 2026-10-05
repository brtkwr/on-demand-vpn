"""Start, stop or check the WireGuard VM, and point a Cloudflare DNS record at its IP."""
import hmac
import os
import time

import functions_framework
import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession

PROJECT, ZONE, VM = os.environ["PROJECT"], os.environ["ZONE"], os.environ["VM"]
VPN_HOST, CF_ZONE = os.environ["VPN_HOST"], os.environ["CF_ZONE"]
TOKEN, CF_TOKEN = os.environ["TOKEN"], os.environ["CF_TOKEN"]
if len(TOKEN) < 32:  # an empty token would let every request in
    raise RuntimeError("TOKEN secret is missing or too short")
PARKED_IP = "192.0.2.1"  # TEST-NET-1: DNS points here while stopped, never at a released IP
ZONE_API = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{ZONE}"
gce = AuthorizedSession(google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])[0])


def vm_state():
    vm = gce.get(f"{ZONE_API}/instances/{VM}").json()
    configs = vm["networkInterfaces"][0].get("accessConfigs", [])
    return vm["status"], configs[0].get("natIP", "") if configs else ""


def point_dns(ip):
    api = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}/dns_records"
    auth = {"Authorization": f"Bearer {CF_TOKEN}"}
    record = {"type": "A", "name": VPN_HOST, "content": ip, "ttl": 60, "proxied": False}
    found = requests.get(api, headers=auth, params={"type": "A", "name": VPN_HOST}, timeout=10).json()["result"]
    if found:
        r = requests.put(f"{api}/{found[0]['id']}", headers=auth, json=record, timeout=10)
    else:
        r = requests.post(api, headers=auth, json=record, timeout=10)
    r.raise_for_status()


def start_and_wait(budget=110):
    """Start the VM and wait for the operation; returns an error message or None."""
    r = gce.post(f"{ZONE_API}/instances/{VM}/start")
    r.raise_for_status()
    op, deadline = r.json(), time.monotonic() + budget
    while op.get("status") != "DONE":  # operations.wait can return early, so loop
        left = deadline - time.monotonic()
        if left <= 0:
            return "timed out waiting for the VM to start"
        op = gce.post(f"{ZONE_API}/operations/{op['name']}/wait", timeout=left + 10).json()
    errors = op.get("error", {}).get("errors", [])
    return errors[0].get("message", errors[0].get("code")) if errors else None


@functions_framework.http
def vpn(request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not hmac.compare_digest(token.encode(), TOKEN.encode()):
        return "forbidden\n", 403
    action = request.args.get("action", "status")
    status, ip = vm_state()
    if action == "start":
        if status == "STOPPING":
            return "still stopping, try again in a minute\n", 409
        if status != "RUNNING":
            error = start_and_wait()
            status, ip = vm_state()
            if error or status != "RUNNING" or not ip:
                return f"start failed: {error or status}\n", 503
            point_dns(ip)
            return f"started {VPN_HOST} -> {ip}\n"
        point_dns(ip)
        return f"already running {VPN_HOST} -> {ip}\n"
    if action == "stop":
        if status not in ("STOPPING", "TERMINATED"):
            gce.post(f"{ZONE_API}/instances/{VM}/stop").raise_for_status()  # don't wait: stopping takes about a minute
            reply = "stopping\n"
        else:
            reply = f"already stopped ({status})\n"
        point_dns(PARKED_IP)
        return reply
    return f"{status} {ip}\n"
