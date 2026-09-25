# Running Anvero on the NAS

The application runs as two containers beside the PostgreSQL one, in
Container Station on the QNAP NAS (`domowy`): `backend` (the API, which
migrates the database when it starts and imports from Allegro on a schedule)
and `web` (nginx: the built interface, and `/api` forwarded to the backend, so
the browser sees one address). Reached at `http://NAS_ADDRESS:8080` on the home
network and, with Tailscale signed in on the machine, from anywhere; the port
is never forwarded on the router (`DECISIONS.md`, 2026-09-21).

**Status: written but not yet run.** Nothing here has been built or started
yet; the first deployment is where it gets checked (`PROJECT_STATUS.md`).

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
   - `DATABASE_URL`: `postgresql+psycopg://anvero:PASSWORD@NAS_LAN_ADDRESS:5432/anvero`,
     the same as in a working machine's `backend/.env`, but with the NAS's
     **LAN address**, not `localhost` (which would be the container itself)
     and not Tailscale's.
   - `SECRET_KEY`: a new random value, at least 32 characters:
     `py -c "import secrets; print(secrets.token_urlsafe(48))"`. It signs the
     login tokens, and this deployment should not share one with a laptop.
4. **Create the application.** Container Station, Applications, Create; paste
   `deploy/docker-compose.yml`, replace the `CHANGE_ME` values, name it
   `anvero`, and create. Do not save the edited copy in Git.
5. **Check.** `http://NAS_ADDRESS:8080/api/v1/health` answers
   `{"status":"ok",...}`; the login page opens at `http://NAS_ADDRESS:8080`;
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

## Creating a user or resetting a password

The scripts are in the backend image. In Container Station open a terminal in
the `backend` container and run, for example,
`python scripts/create_user.py you@example.com` or
`python scripts/reset_password.py you@example.com`.

## Limits

- Plain HTTP. On the home network and through Tailscale that is acceptable
  (Tailscale encrypts its own traffic); from a café's Wi-Fi without Tailscale
  it would not be, which is why the port stays off the internet.
- The backend image carries the test and lint tools too, since
  `requirements.txt` is one file. Harmless, only larger.
- One backend only: no leader election for the scheduled import.
- The backup covers the database (`DEVELOPMENT.md`); the containers hold no
  data of their own and can be recreated at any time.
