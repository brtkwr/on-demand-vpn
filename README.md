# on-demand-vpn

A personal WireGuard VPN on a GCP spot VM that stays stopped until you need it. A small Cloud Run function starts or stops the VM and points a Cloudflare DNS record at its new IP, so every client connects to the same hostname even though the VM's IP changes on each start.

- `function/`: the `vpn-switch` Cloud Run function (`?action=start|stop|status`, bearer token).
- `vpn`: laptop script, `vpn up|down|status`.
- `add-peer.sh`: add a client device (key generated locally, QR code for phones).
- `server/setup.sh`: one-off WireGuard setup on the VM.
- `deploy.sh`: deploy the function.

All deployment-specific values live in `.env` (gitignored). Copy `.env.example` to start.

## Cost

With a spot `f1-micro` on the Standard network tier: about $0.48/month stopped (the 10 GB disk), about $0.0034/hour running, and the first 200 GiB of egress each month free. The function, secrets and image fit in the free tiers. These are list prices, not a bill.

## Setup from scratch

You need `gcloud`, `wireguard-tools`, a GCP project, and a domain on Cloudflare. Fill in `.env` first; the commands below use its values.

```bash
set -a; . ./.env; set +a
G=(--project "$GCP_PROJECT")

# VM and firewall
gcloud compute firewall-rules create allow-wireguard "${G[@]}" \
  --network default --allow udp:51820 --source-ranges 0.0.0.0/0 --target-tags wireguard
gcloud compute instances create "$VM" "${G[@]}" --zone "$ZONE" \
  --machine-type f1-micro --provisioning-model SPOT --instance-termination-action STOP \
  --network-tier STANDARD --image-family debian-13 --image-project debian-cloud \
  --boot-disk-size 10GB --boot-disk-type pd-standard \
  --tags wireguard --no-service-account --no-scopes
gcloud compute scp server/setup.sh "$VM":/tmp/ "${G[@]}" --zone "$ZONE"
gcloud compute ssh "$VM" "${G[@]}" --zone "$ZONE" --command 'sudo bash /tmp/setup.sh'

# Function identity: start/stop on this one VM only
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com "${G[@]}"
gcloud iam service-accounts create vpn-switch "${G[@]}"
gcloud iam service-accounts create vpn-switch-build "${G[@]}"
gcloud iam roles create vpnSwitch "${G[@]}" \
  --permissions compute.instances.get,compute.instances.start,compute.instances.stop,compute.zoneOperations.get
gcloud compute instances add-iam-policy-binding "$VM" "${G[@]}" --zone "$ZONE" \
  --member "serviceAccount:vpn-switch@$GCP_PROJECT.iam.gserviceaccount.com" \
  --role "projects/$GCP_PROJECT/roles/vpnSwitch"
for r in roles/cloudbuild.builds.builder roles/logging.logWriter roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --condition=None \
    --member "serviceAccount:vpn-switch-build@$GCP_PROJECT.iam.gserviceaccount.com" --role "$r"
done

# Secrets: a random caller token, and a Cloudflare token with Zone:Read + DNS:Edit on one zone
python3 -c 'import secrets;print(secrets.token_urlsafe(32),end="")' | \
  gcloud secrets create vpn-switch-token --data-file=- "${G[@]}"
pbpaste | tr -d '\n' | gcloud secrets create vpn-switch-cf-token --data-file=- "${G[@]}"  # token on clipboard
for s in vpn-switch-token vpn-switch-cf-token; do
  gcloud secrets add-iam-policy-binding "$s" "${G[@]}" --role roles/secretmanager.secretAccessor \
    --member "serviceAccount:vpn-switch@$GCP_PROJECT.iam.gserviceaccount.com"
done

./deploy.sh
```

Then start the VM (`./vpn status` should answer, then call `start` once) and add each device:

```bash
./add-peer.sh laptop 10.8.0.2   # move laptop.conf to the WG_CONF path in .env
./add-peer.sh iphone 10.8.0.3   # scan iphone.png in the WireGuard app, then delete both files
```

On macOS, `brew install wireguard-tools` provides `wg` and `wg-quick`. Symlink `vpn` onto your `PATH`.

## iPhone

A Shortcut with _Choose from Menu_ (start, stop), then _Get Contents of URL_ on `https://<region>-<project>.cloudfunctions.net/vpn-switch?action=<choice>` with a header `Authorization: Bearer <token>`, then _Show Result_. Switch the tunnel on in the WireGuard app once `start` returns.

## Notes

- `start` waits for the VM and updates DNS before it returns, about 40 seconds from stopped. Replies: `started <host> -> <ip>`, `already running <host> -> <ip>`, `stopping`, `already stopped (<state>)`, or 409 while the VM is still stopping.
- Spot VMs can be reclaimed. The VM then stops, and the next `start` brings it back with a new IP.
- The token can only start or stop this VM. Rotate it by adding a new version of `vpn-switch-token` and redeploying.
