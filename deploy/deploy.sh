#!/bin/sh
# Deploy the pushed main branch to the host.
#
#   deploy/deploy.sh
#
# Refuses unless this checkout is clean and level with origin/main, because the host
# installs with git pull. On the host: pull, sync the virtualenv, back up and migrate the
# database (cookbook migrate), install any changed systemd units, restart the app and
# check /healthz.
#
# Host and user come from deploy/host.env (DEPLOY_HOST, DEPLOY_USER; see
# host.env.example).
set -eu

cd "$(dirname "$0")/.."
. deploy/host.env

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
if [ -n "$changed" ]; then
	echo "units updated:$changed"
	sudo systemctl daemon-reload
	case "$changed" in *cookbook-mdns.service*) sudo systemctl restart cookbook-mdns ;; esac
fi
sudo systemctl restart cookbook
sleep 3
echo "deployed $(git log -1 --format='%h %s')"
echo "healthz on the host: $(curl -fsS -m 10 http://localhost/healthz)"
EOF
