# cookbook

A small, self-hosted recipe web app for a home network, built for phones in the kitchen.
Recipes live in one SQLite database; this repository holds only the code: no recipes.

Status: early. Browsing and search work: full-text search with filters (tags, source,
ingredient, times, serves, notes), recipe, tag, source and notes pages, images and a JSON
API. Anyone can read notes; a signed-in user adds, edits and deletes them, and ticks the
recipes they have cooked, which then show as Cooked rather than New (and can be filtered). Any recipe exports
as an A4 PDF (with or without notes) or as a zipped draft folder; signed-in users can
download every recipe as one zip. In the kitchen, ingredients and steps tick off, the
current step is marked, the quantities scale with the serves and switch to metric, and the
screen stays awake; all of it is remembered per phone. The site can be added to a phone's
home screen, and a recipe link shared in a chat app previews with its title, intro and
card image (Open Graph tags; the sending phone must be on the home network to fetch them).

There is one account and no sign-up. It is created on the host with recipe-db's
`set-password` command, which writes an scrypt hash to the `users` table; running it again
replaces the account's email and password, and the database refuses a second account.
Setting a new password signs out every device.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run scripts/lint-and-test.sh   # ruff, format check, mypy --strict, pytest
```

Run the app against a database (created by the migrations and filled by an import):

```bash
COOKBOOK_DB_PATH=path/to/recipes.db COOKBOOK_SECRET_KEY=$(openssl rand -hex 32) \
  uv run uvicorn --factory cookbook.app:create_app --reload
```

## Layout

| Path | |
|---|---|
| `src/cookbook/app.py` | `create_app()`: the FastAPI app; refuses to start on a database at another schema version |
| `src/cookbook/queries.py` | Reads recipes, tags, sources and notes into the models the pages show |
| `src/cookbook/routes/` | Pages (`pages.py`), sign-in (`auth.py`), note writes (`notes.py`) and the JSON API with `/healthz` (`api.py`) |
| `src/cookbook/auth.py`, `notes.py` | Signing in and the session cookie's contents; adding, editing and deleting notes |
| `src/cookbook/templates/`, `static/` | Jinja2 templates, CSS, scripts and the bundled Inter font (SIL OFL, `static/fonts/OFL.txt`) |
| `src/cookbook/migrations/` | Database schema as numbered SQL migrations (`schema.migrate`) |
| `src/cookbook/draft.py` | `RecipeDraft`: a recipe as a TOML file, for import and export |
| `src/cookbook/units.py` | Parses quantities such as `1½ cups` or `2 tbsp + 1 tsp` into grams or millilitres; marks the numbers the browser may scale; works out serves options, metric amounts and °F / inch conversions |
| `src/cookbook/densities.toml` | Grams per millilitre for showing volumes such as cups of flour in grams |
| `src/cookbook/static/cook.js` | Cook mode: ticks, current step, serves scaling, metric view, keeping the screen awake |
| `src/cookbook/search.py` | Searches and filters recipes, and keeps a recipe's full-text search index current |
| `src/cookbook/export.py` | PDF and draft exports, built on request |
| `src/cookbook/fonts/` | Inter TrueType subsets for the PDF (SIL OFL, `OFL.txt`) |
| `src/cookbook/static/htmx.min.js` | [htmx](https://htmx.org) 2.0.4, vendored release build (BSD-0) |
| `src/cookbook/passwords.py` | Hashes and verifies the admin password (scrypt) |
| `src/cookbook/cli.py` | The `cookbook` command: `migrate` and `backup` |
| `deploy/` | systemd units for the app, mDNS and nightly backups, the `Caddyfile` and Caddy drop-in for HTTPS, and `deploy.sh` for updates; host specifics stay in the git-ignored `host.env` and `local/` |
| `src/cookbook/settings.py` | Configuration from `COOKBOOK_*` environment variables |

## Configuration

| Variable | |
|---|---|
| `COOKBOOK_DB_PATH` | Path to the SQLite database (required) |
| `COOKBOOK_SECRET_KEY` | Session signing key, at least 32 characters (required) |
| `COOKBOOK_HOST`, `COOKBOOK_PORT` | Listen address, default `127.0.0.1:8000` |
| `COOKBOOK_MIGRATE` | Apply pending migrations at startup, default off |
| `COOKBOOK_FAILED_LOGIN_DELAY_S` | Seconds a failed sign-in waits before answering, default 1 |
| `COOKBOOK_SECURE_COOKIE` | Mark the session cookie Secure (HTTPS only), default off; on where the site is served over HTTPS |

## Command line

| Command | |
|---|---|
| `cookbook migrate --db PATH` | Copy the database to `PATH.bak`, then apply pending migrations |
| `cookbook backup --db PATH --to DIR [--keep 30]` | Copy the database into `DIR` as `recipes-<UTC time>.db`, checked with SQLite's integrity check, keeping the newest 30. `DIR` must exist, so an unmounted backup disk fails the run instead of filling the disk underneath |

## Deploying

The app runs on a small Linux host on the home network (such as a Raspberry Pi) under
systemd, as an unprivileged `cookbook` user, from `/srv/cookbook`. The unit files are in
`deploy/`; anything specific to one host goes in `deploy/host.env` and `deploy/local/`,
which are git-ignored.

The app listens only on `127.0.0.1:8000`. [Caddy](https://caddyserver.com) serves it at
`https://cookbook.<name>.duckdns.org`, a free [DuckDNS](https://www.duckdns.org) name whose
address is the host's reserved (private) address: it resolves anywhere but leads somewhere
only on the home network. Caddy gets a Let's Encrypt certificate, with ZeroSSL as fallback,
through the DNS challenge, so nothing is opened on the router, and renews it by itself.
Plain HTTP by any name, `cookbook.local` included, forwards to the HTTPS site.

Before the first install:

- At DuckDNS, create the name and set its address ("current ip") to the host's reserved
  address; DuckDNS fills in the public address of the browser that created it. Keep the
  account token private: it controls every name on the account.
- If the router's DNS drops public answers that point at private addresses (DNS rebinding
  protection), add a local DNS record for `cookbook.<name>.duckdns.org` on the network's
  own DNS server. That record also keeps the name working when the internet is down.

The packaged Caddy has no DuckDNS plugin, and Caddy's download page builds plugins only for
signed-in users, so build the binary with Caddy's builder image on any machine with Docker,
for the host's architecture and the packaged version (`caddy version` on the host):

```bash
docker run --rm -e GOOS=linux -e GOARCH=arm64 -e CGO_ENABLED=0 -v "$PWD":/out \
  caddy:2.11.9-builder xcaddy build v2.11.9 --with github.com/caddy-dns/duckdns --output /out/caddy
```

and copy `caddy` to the host. First install, on the host:

```bash
sudo apt install avahi-utils
# Caddy from its apt repository (https://caddyserver.com/docs/install#debian-ubuntu-raspbian),
# held off port 80 until it is configured
sudo systemctl disable --now caddy
# The DuckDNS build in place of the packaged binary (caddy list-modules shows
# dns.providers.duckdns); apt upgrades then go to caddy.default
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy
sudo install -m 0755 caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo adduser --system --group --no-create-home cookbook
sudo install -d -o <user> /srv/cookbook /srv/cookbook/python
sudo install -d -o cookbook -g cookbook -m 0700 /srv/cookbook/data
git clone https://github.com/<owner>/cookbook /srv/cookbook/cookbook
cd /srv/cookbook/cookbook
# Python outside /home: the service's ProtectHome would hide it
UV_PYTHON_INSTALL_DIR=/srv/cookbook/python uv sync --frozen --no-dev --compile-bytecode
```

Then the environment files under `/etc/cookbook/`, readable by root only:

| File | Holds |
|---|---|
| `cookbook.env` | `COOKBOOK_DB_PATH=/srv/cookbook/data/recipes.db`, `COOKBOOK_SECRET_KEY=` (`openssl rand -hex 32`), `COOKBOOK_SECURE_COOKIE=true` |
| `caddy.env` | `COOKBOOK_DOMAIN=<name>.duckdns.org`, `COOKBOOK_ACME_EMAIL=` an address for the certificate authorities' expiry notices, `DUCKDNS_TOKEN=` the DuckDNS account token |
| `mdns.env` | `COOKBOOK_MDNS_ADDRESS=` the host's reserved address |
| `backup.env` | `COOKBOOK_DB_PATH` as above, `COOKBOOK_BACKUP_DIR=` an existing directory, ideally on another disk |

Copy `deploy/*.service` and `deploy/*.timer` to `/etc/systemd/system/`,
`deploy/caddy.service.d/` to `/etc/systemd/system/caddy.service.d/` and `deploy/Caddyfile`
to `/etc/caddy/Caddyfile`, plus any drop-ins from `deploy/local/`, then
`sudo systemctl daemon-reload` and
`sudo systemctl enable --now cookbook cookbook-mdns caddy cookbook-backup.timer`.
`journalctl -u caddy` shows the certificate being issued, within a minute or two.

The database arrives once, before anyone writes a note; afterwards recipes only come in
through recipe-db's import. Bring it to the current schema as the `cookbook` user:
`sudo -u cookbook /srv/cookbook/cookbook/.venv/bin/cookbook migrate --db /srv/cookbook/data/recipes.db`.
The one account is created with recipe-db's `set-password`.

Updates: push `main`, then run `deploy/deploy.sh` from the laptop. It refuses unless the
checkout is clean and level with `origin/main`; on the host it pulls, runs
`uv sync --frozen --no-dev`, `cookbook migrate` (which backs the database up first),
installs any changed unit files, Caddy drop-ins and `Caddyfile` (restarting or reloading
Caddy), restarts the app and checks `/healthz`; then, from the laptop, it checks `/healthz`
over HTTPS and prints the certificate's expiry date. It refuses a host without Caddy, where
the app would be unreachable. The host, user and site URL come from `deploy/host.env`.

Caddy updates: apt keeps upgrading the packaged binary (`caddy.default`), but the one that
runs is the DuckDNS build, which apt never touches. To update it, build again with the new
version in both places in the `docker run` line, install it over `/usr/bin/caddy.custom`
and `sudo systemctl restart caddy`.
