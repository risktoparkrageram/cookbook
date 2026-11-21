#!/bin/sh
# Deploy the pushed main branch to the host.
#
#   deploy/deploy.sh
#
# Refuses unless this checkout is clean and level with origin/main, because the host
# installs with git pull. On the host: refuse if Caddy isn't installed (the app listens only
# on 127.0.0.1, so without Caddy nobody could reach it), pull, sync the virtualenv, back up
# and migrate the database (cookbook migrate), install any changed systemd units, Caddy
# drop-ins and Caddyfile, restart the app and check /healthz. Then, from here, check
# /healthz over HTTPS and print the certificate's expiry date.
#
# Host, user and site URL come from deploy/host.env (DEPLOY_HOST, DEPLOY_USER, DEPLOY_URL;
# see host.env.example).
set -eu

cd "$(dirname "$0")/.."
. deploy/host.env
: "${DEPLOY_URL:?set DEPLOY_URL in deploy/host.env}"

git fetch -q origin
if [ -n "$(git status --porcelain)" ]; then
	echo "commit or stash your changes first" >&2
	exit 1
fi
commit=$(git rev-parse HEAD)
if [ "$commit" != "$(git rev-parse origin/main)" ]; then
	echo "this checkout is not level with origin/main: push (or pull) first" >&2
	exit 1
fi

ssh -o BatchMode=yes "$DEPLOY_USER@$DEPLOY_HOST" 'sh -s' -- "$commit" <<'EOF'
set -eu
if ! command -v caddy >/dev/null; then
	echo "Caddy isn't installed on the host: install it first (README.md, Deploying)" >&2
	exit 1
fi
cd /srv/cookbook/cookbook
git pull -q --ff-only
if [ "$(git rev-parse HEAD)" != "$1" ]; then
	echo "the host's checkout is not at the pushed commit" >&2
	exit 1
fi
UV_PYTHON_INSTALL_DIR=/srv/cookbook/python "$HOME/.local/bin/uv" sync -q --frozen --no-dev \
	--compile-bytecode
sudo sh -c '. /etc/cookbook/cookbook.env &&
	sudo -u cookbook /srv/cookbook/cookbook/.venv/bin/cookbook migrate --db "$COOKBOOK_DB_PATH"'

changed=""
for unit in deploy/*.service deploy/*.timer; do
	name=$(basename "$unit")
	if ! cmp -s "$unit" "/etc/systemd/system/$name"; then
		sudo install -m 0644 "$unit" "/etc/systemd/system/$name"
		changed="$changed $name"
	fi
done
sudo install -d /etc/systemd/system/caddy.service.d
for dropin in deploy/caddy.service.d/*.conf; do
	name=caddy.service.d/$(basename "$dropin")
	if ! cmp -s "$dropin" "/etc/systemd/system/$name"; then
		sudo install -m 0644 "$dropin" "/etc/systemd/system/$name"
		changed="$changed $name"
	fi
done
caddyfile_changed=no
if ! cmp -s deploy/Caddyfile /etc/caddy/Caddyfile; then
	sudo install -m 0644 deploy/Caddyfile /etc/caddy/Caddyfile
	caddyfile_changed=yes
fi
if [ -n "$changed" ]; then
	echo "units updated:$changed"
	sudo systemctl daemon-reload
	case "$changed" in *cookbook-mdns.service*) sudo systemctl restart cookbook-mdns ;; esac
fi
case "$changed" in
*caddy.service.d/*) sudo systemctl restart caddy ;;
*) if [ "$caddyfile_changed" = yes ]; then sudo systemctl reload-or-restart caddy; fi ;;
esac
sudo systemctl restart cookbook
sleep 3
echo "deployed $(git log -1 --format='%h %s')"
echo "healthz on the host: $(curl -fsS -m 10 http://127.0.0.1:8000/healthz)"
EOF

echo "healthz over HTTPS: $(curl -fsS -m 10 "$DEPLOY_URL/healthz")"
site=${DEPLOY_URL#https://}
site=${site%%/*}
echo "certificate $(openssl s_client -connect "$site:443" -servername "$site" </dev/null 2>/dev/null |
	openssl x509 -noout -enddate)"
