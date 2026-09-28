# Running Anvero on the NAS

The application runs as two containers beside the PostgreSQL one, in
Container Station on the QNAP NAS (`domowy`): `backend` (the API, which
migrates the database when it starts and imports from Allegro on a schedule)
and `web` (nginx: the built interface, and `/api` forwarded to the backend, so
the browser sees one address). Reached at `http://NAS_ADDRESS:8081` on the home
network and, with Tailscale signed in on the machine, from anywhere; the port
is never forwarded on the router (`DECISIONS.md`, 2026-09-21).

**Status: first deployment done, 2026-09-27.** Running on the QNAP NAS
(`domowy`, TS-251) in Container Station, alongside the existing PostgreSQL
stack. Two things differed from the plan below and are now permanent
(`DECISIONS.md`, 2026-09-27):

- **Port 8081, not 8080.** The NAS's own `apache_proxy` service already binds
  8080; `docker compose up` failed with `address already in use` until the
  published port was changed.
- **`DATABASE_URL` points at the database container's name, not the NAS's LAN
  address.** The backend and the database are two separate `docker compose`
  stacks, each with its own default Docker network; connecting from inside
  the backend container to the NAS's own LAN address timed out
  (`ConnectionTimeout`), unlike a real machine on the network reaching the
  published port. Fixed by joining the backend's network to the database
  stack's (`docker network connect`, or `networks:` in the compose file, now
  reflected in `deploy/docker-compose.yml`) and pointing `DATABASE_URL` at the
  database container's name instead.

While cleaning this up, nine leftover `alleintegrator-customer-*` containers
and their images from earlier integration testing were removed from the NAS,
reclaiming about 1 GB.

## How the images get there

`.github/workflows/publish.yml` builds `backend/Dockerfile` and
`frontend/Dockerfile` for `linux/amd64` and `linux/arm64` and publishes them to
`ghcr.io/dev-chintz/anvero-backend` and `anvero-web`, tagged `latest` and with
the commit's short hash, after **Checks** succeeded for a push to `main`.
Watch it under the repository's Actions tab. The images hold no secrets; all
settings come from the container's environment.

## First deployment

1. **Let GitHub build the images.** Push to `main` (or re-run the *Publish
   images* workflow) and wait for it to go green. Under the account's
   Packages, both images should appear.
2. **Let the NAS pull them.** GitHub packages start private. Either make the
   two packages public (Package settings, Change visibility; sensible if the
   repository is public), or create a personal access token with only the
   `read:packages` permission and add the registry in Container Station
   (Registries: `ghcr.io`, user `dev-chintz`, the token as password).
3. **Get the values.**
   - `DATABASE_URL`: `postgresql+psycopg://anvero:PASSWORD@DB_CONTAINER_NAME:5432/anvero`,
     using the **database container's name** on its own stack's Docker
     network (not `localhost`, which is this container, and not the NAS's LAN
     address - see "Status" above for why). Join the backend to that
     network first (`docker network connect DB_STACK_NETWORK backend`, or the
     `networks:` block already in `deploy/docker-compose.yml`).
   - `SECRET_KEY`: a new random value, at least 32 characters:
     `py -c "import secrets; print(secrets.token_urlsafe(48))"`. It signs the
     login tokens, and this deployment should not share one with a laptop.
4. **Create the application.** Container Station, Applications, Create; paste
   `deploy/docker-compose.yml`, replace the `CHANGE_ME` values, name it
   `anvero`, and create. Do not save the edited copy in Git.
5. **Check.** `http://NAS_ADDRESS:8081/api/v1/health` answers
   `{"status":"ok",...}`; the login page opens at `http://NAS_ADDRESS:8081`;
   the accounts are the ones already in the shared database. The backend's log
   (Container Station, the container's Logs) should say
   `Imports scheduled every 15 minutes unless Integrations says otherwise`.
6. **Laptops need no change.** Backends sharing the database take turns at the
   schedule (one holds a lease), so a laptop's backend waits while the NAS one runs it
   and takes over only when the NAS has been silent for two minutes. To keep a
   laptop from ever taking over, set `SCHEDULER_ENABLED=false` in its `backend/.env`
   (`INTEGRATIONS.md`). The interval is set in Integrations, not in a file.

## Updating

After a push to `main` whose Actions runs are green, in Container Station open
the `anvero` application and recreate it with the latest images (pull, then
recreate). The backend migrates the database as it starts. To go back, put a
commit's short hash in place of `latest` in the compose file and recreate.

**Not yet reconciled with the above:** the 2026-09-27 deployment session
updated the running application over SSH instead, from a git clone on the
NAS at `/share/CACHEDEV1_DATA/Kopie/container-station-data/application/anvero/`:
`git pull`, `docker compose build`, `docker compose up -d`. Whether that clone
has a `build:` context (bypassing the published GHCR images and the Actions
workflow entirely) or the checked-in `image:` references (in which case
`build` was a no-op and `up -d` alone would have sufficed) is unconfirmed -
check `deploy/docker-compose.yml` **as saved on the NAS**, which is not in
Git, before relying on either update path. This gap is also why "automatic
update detection and a Settings button to trigger it" is the next planned
piece of deployment work (`ROADMAP.md`, "Somewhere to run").

## Encrypting the integration secrets

Allegro's refresh token and client secret and InPost's token are kept in the
database, so the nightly dump holds them too. To store them encrypted (`GDPR.md`,
"Secrets"): in the `backend` container's terminal run
`python scripts/encrypt_secrets.py --new-key`, put the printed value in the
compose file as `SECRETS_KEY` (the commented line beside `SECRET_KEY`), save a
copy in the password manager, redeploy, then run
`python scripts/encrypt_secrets.py` once. Every backend using this database, a
laptop's included, needs the same value; a backend without it cannot read the
secrets, and a lost key means authorizing Allegro and entering the secrets again.

## Creating a user or resetting a password

The scripts are in the backend image. In Container Station open a terminal in
the `backend` container and run, for example,
`python scripts/create_user.py you@example.com` or
`python scripts/reset_password.py you@example.com`.

## Limits

- Plain HTTP. On the home network and through Tailscale that is acceptable
  (Tailscale encrypts its own traffic, end to end, WireGuard); from a café's
  Wi-Fi without Tailscale it would not be, which is why the port stays off the
  internet: no router forward, and nothing reaches it from outside but the
  tailnet. So the answer to "how is the connection encrypted" (`GDPR.md`) is
  Tailscale, not HTTPS. Should the page ever need to be reached without
  Tailscale, it needs HTTPS in front of it first (`tailscale serve`, or a
  reverse proxy with a certificate).
- The backend image carries the test and lint tools too, since
  `requirements.txt` is one file. Harmless, only larger.
- One backend only: no leader election for the scheduled import.
- The backup covers the database (`DEVELOPMENT.md`); the containers hold no
  data of their own and can be recreated at any time.
