# AGENTS.md

Personal on-demand WireGuard VPN: a GCP spot VM plus a Cloud Run function (`vpn-switch`) that starts/stops it and updates a Cloudflare DNS record. See README.md for layout and setup.

## Never commit deployment details

This repo is public. Every value that identifies the live deployment lives in `.env` (gitignored): GCP project, account, region, zone, VM name, the VPN hostname/domain, the Cloudflare zone ID, client config paths. Do not write any of them into code, docs, commit messages, PR text or examples. Use the placeholders from `.env.example` (`my-project`, `vpn.example.com`, `<region>-<project>`). Also never commit WireGuard keys, client `.conf` files, QR images, tokens, or IP addresses. Before pushing, grep the diff for the real values in `.env`.

## Working on it

- Scripts source `env.sh`, which loads `.env` and sets `GCLOUD` (project/account flags) and `FUNCTION_URL`.
- Deploy the function with `./deploy.sh`; check it with `./vpn status`.
- `start` on a stopped VM costs money while it runs; stop it again when testing (`./vpn down` or `?action=stop`).
- Secrets are in Secret Manager (`vpn-switch-token`, `vpn-switch-cf-token`). Read them into variables or pipes, never print them.
- Run `shellcheck -S warning vpn deploy.sh add-peer.sh env.sh server/setup.sh` after editing scripts.
- After editing the function, run `uv run --with functions-framework --with google-auth --with requests python function/test_main.py`. It fakes the Compute API, so it costs nothing; `function/.gcloudignore` keeps it out of deploys.

## Gotchas

- Don't name a function env var `HOST`: the functions framework's server binds to it.
- `google-cloud-compute` exceeds the 256 MiB limit; the function calls the Compute REST API through `google-auth` instead.
- The project's default compute service account may not exist, so the build uses its own service account (`vpn-switch-build`).
- `vpn up` parses the IP as the last word of the `start` reply; keep replies to `start` ending with the IP.
- The VPC MTU is 1460, so the server's wg0 is 1380 and `server/setup.sh` clamps TCP MSS to 1340. Clients set `MTU = 1380`.
