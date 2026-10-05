"""Checks the switch function's branches against a fake Compute API: python function/test_main.py"""
import importlib
import os
import sys
from unittest import mock

os.environ.update(PROJECT="p", ZONE="z", VM="vm", VPN_HOST="vpn.example.com", CF_ZONE="cf", TOKEN="t" * 32, CF_TOKEN="x")
sys.path.insert(0, os.path.dirname(__file__))


class Resp:
    def __init__(self, body=None, status=200):
        self.body, self.status_code = body or {}, status

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeGCE:
    """Instance states returned in order by get(); operation results returned in order by wait."""

    def __init__(self, states, ops=()):
        self.states, self.ops, self.calls = list(states), list(ops), []

    def get(self, url):
        status, ip = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        configs = [{"natIP": ip}] if ip else [{}]
        return Resp({"status": status, "networkInterfaces": [{"accessConfigs": configs}]})

    def post(self, url, timeout=None):
        self.calls.append(url.rsplit("/", 1)[-1])
        if url.endswith("/start"):
            return Resp({"name": "op1", "status": "RUNNING"})
        if url.endswith("/wait"):
            return Resp(self.ops.pop(0))
        return Resp()


def load():
    with mock.patch("google.auth.default", return_value=(object(), "p")), \
         mock.patch("google.auth.transport.requests.AuthorizedSession"):
        return importlib.reload(importlib.import_module("main"))


class Req:
    def __init__(self, action=None, token="t" * 32):
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.args = {"action": action} if action else {}


def run(main, gce, action, **kw):
    main.gce, dns = gce, []
    main.point_dns = dns.append
    out = main.vpn(Req(action, **kw))
    body, code = out if isinstance(out, tuple) else (out, 200)
    return body.strip(), code, dns


main = load()
assert run(main, FakeGCE([("TERMINATED", "")]), "start", token=None)[1] == 403
assert run(main, FakeGCE([("TERMINATED", "")]), "start", token="wrong")[1] == 403

# start: wait returns early once, then DONE; DNS only updated with the running IP
gce = FakeGCE([("TERMINATED", ""), ("RUNNING", "1.2.3.4")], ops=[{"name": "op1", "status": "RUNNING"}, {"name": "op1", "status": "DONE"}])
body, code, dns = run(main, gce, "start")
assert (code, dns, gce.calls) == (200, ["1.2.3.4"], ["start", "wait", "wait"]), (body, code, dns, gce.calls)

# start: operation reports an error (e.g. no spot capacity) -> 503 with the reason, DNS untouched
gce = FakeGCE([("TERMINATED", "")], ops=[{"status": "DONE", "error": {"errors": [{"code": "ZONE_RESOURCE_POOL_EXHAUSTED", "message": "no capacity"}]}}])
body, code, dns = run(main, gce, "start")
assert (code, dns) == (503, []) and "no capacity" in body, (body, code, dns)

# start: operation DONE but VM not running / no IP -> 503, DNS untouched
body, code, dns = run(main, FakeGCE([("TERMINATED", "")], ops=[{"status": "DONE"}]), "start")
assert (code, dns) == (503, []), (body, code, dns)

# start while running re-points DNS; start while stopping is a 409
assert run(main, FakeGCE([("RUNNING", "5.6.7.8")]), "start")[::2] == ("already running vpn.example.com -> 5.6.7.8", ["5.6.7.8"])
assert run(main, FakeGCE([("STOPPING", "")]), "start")[1] == 409

# stop parks DNS whether or not the VM was running
body, code, dns = run(main, FakeGCE([("RUNNING", "5.6.7.8")]), "stop")
assert (body, dns) == ("stopping", [main.PARKED_IP]), (body, dns)
body, code, dns = run(main, FakeGCE([("TERMINATED", "")]), "stop")
assert (body, dns) == ("already stopped (TERMINATED)", [main.PARKED_IP]), (body, dns)

# status and unknown actions report state without changing anything
assert run(main, FakeGCE([("RUNNING", "5.6.7.8")]), None)[::2] == ("RUNNING 5.6.7.8", [])

# a missing or short token refuses to load
os.environ["TOKEN"] = ""
try:
    load()
    raise AssertionError("empty TOKEN should refuse to load")
except RuntimeError:
    pass
print("all function checks passed")
