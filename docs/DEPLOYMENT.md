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

**Confirmed 2026-09-27:** the NAS's application directory
(`/share/CACHEDEV1_DATA/Kopie/container-station-data/application/anvero/`)
holds only `docker-compose.yml` (plus Container Station's own
`docker-compose.resource.yml` for CPU/memory limits) - no git clone, no
`build:` context. The above is the only real update path; an earlier session
had instead run `git pull` and `docker compose build` there, but there is
nothing to pull or build in that directory, so that must have targeted a
different, no-longer-present location, or a misremembered command. Manually
running `docker compose pull && docker compose up -d` (equivalent to
Container Station's recreate) is the whole update, which is also why
"automatic update detection and a Settings button to trigger it" is the next
planned piece of deployment work (`ROADMAP.md`, "Somewhere to run").

## Updating from Settings

Once set up, an administrator sees "An Anvero update is available" above every
page when a newer version is published, and installs it from Settings,
Updates, with one button (`API.md`, "Updates"). It works only with the
published images (`image: ghcr.io/...` in the compose file on the NAS, not
`build:`), which is also what makes the NAS run only what passed the checks.

Setting it up, once:

1. Make the `anvero-updater` package public on GitHub, like the other two
   (Packages, Package settings, Change visibility), after the first push that
   publishes it.
2. Generate a token: `py -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. In the compose file on the NAS, add `UPDATER_TOKEN` to the backend and the
   whole `updater` service, as in `deploy/docker-compose.yml`, with that token
   in both places. The updater mounts the compose file itself
   (`./docker-compose.yml`, relative to the application's folder,
   `/share/CACHEDEV1_DATA/Kopie/container-station-data/application/anvero/`):
   check the file there is really named so, and change the left side if not.
4. Recreate the application. Settings, Updates should then say which version
   runs; "Check now" asks GitHub at once.

What happens on the button: the backend asks the updater (`http://updater:8080`,
no published port, the token), which runs
`docker compose -f /project/docker-compose.yml pull backend web` and
`up -d --no-deps backend web`. The backend migrates as it starts, as always. While
it runs, the page shows the steps and a progress bar over the whole application,
which cannot be used meanwhile. Every update, and every version the backend finds
itself on at start, is in Settings, Updates, "Update history"; a failed run shows
what it printed there. The updater never recreates
itself; a newer updater image is taken up by recreating the application by hand,
which is also the way back: put a commit's short hash in place of `latest` and
recreate.

The updater holds the Docker socket, which is as good as root on the NAS. That
is why it has no port, answers only the token, can run only those two commands,
and why only an administrator sees the button.

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

## The assortment's pictures

The assortment page keeps a copy of every offer's pictures on the NAS (`CATALOG.md`), under
`/app/data/catalog_images` in the backend container (`CATALOG_IMAGES_DIR`). Without a mounted folder they
live inside the container and are thrown away by every update from Settings, then downloaded again: it works,
but it is a few thousand downloads for nothing. So, once:

1. On the NAS, make a folder for them beside the application's other files (say `catalog-images`) and give it to
   the backend's user, which is `1000`: `chown 1000 catalog-images` (File Station cannot set an owner; SSH can).
2. In the application's `docker-compose.yml` on the NAS (not the copy in Git, which is a template), add under
   the `backend` service a `volumes:` entry with the folder's **absolute** path, say
   `/share/CACHEDEV1_DATA/Kopie/container-station-data/application/anvero/catalog-images:/app/data/catalog_images`
   (the template in `deploy/docker-compose.yml` shows where), then recreate the application. Not `./catalog-images`:
   the update button runs `docker compose` inside the updater container, where `./` is `/project`, and the Docker
   daemon would read that as a path on the NAS (an empty folder owned by root, unwritable by the backend). This is
   reasoning from how Docker resolves bind paths; the update button has not been run with the mount yet
   (`PROJECT_STATUS.md`).
3. Check: `docker exec <backend container> sh -c 'touch /app/data/catalog_images/.test && rm /app/data/catalog_images/.test && echo OK'`
   prints `OK`. Container Station's "Create again" (the application's list, YAML editor) deletes the application's
   folder, `catalog-images` with it, and Docker then makes it again owned by root: run `chown 1000 catalog-images` once
   more afterwards (this happened on 2026-10-03). Updating through Settings or `docker compose up -d` does not do this.

The first full read on the real account (2026-10-03) stored about 1.5 MB per picture, 1.8 GB for the first 1194
files; with some 20 000 pictures, some of them shared, expect tens of GB. The files are named by their hash, so a
picture used by several offers is one file.

If the folder cannot be written the sync still reads the offers and says "The pictures folder is not writable"
instead of failing; the pictures then show from Allegro's addresses. The folder is not in the database dump; a
lost one is downloaded again by the next sync, which notices the missing files. Backing it up is optional.

## Creating a user or resetting a password

The scripts are in the backend image. In Container Station open a terminal in
the `backend` container and run, for example,
`python scripts/create_user.py you@example.com` or
`python scripts/reset_password.py you@example.com`.

## The log

The backend and the web container write to their standard output, so their logs are the
containers' own: in Container Station the container's Logs, or `docker logs`. The security events
are lines of the backend's log with `| security |` in them (logins, refused logins and why,
requests stopped by a rate limit, accounts made or changed; `GDPR.md`, "The security log"), for
example `docker logs <backend container> 2>&1 | grep "| security |"`. The `2>&1` matters: the
backend logs to stderr, which `docker logs` hands on separately, so without it the pipe gets
nothing and grep filters nothing (the whole log scrolls past).

**What each access log writes.** The backend's (uvicorn) and the web container's (nginx) both write
the address a request came from and the path called, without what follows a `?`, and mark a dropped
query `?...`. A search typed in the interface travels as `?search=<what was typed>`, often a buyer's
name (`GDPR.md`, "Addresses and the browser's history"). The backend's has done so since 2026-09-17;
nginx's only since 2026-10-01 (`frontend/nginx.conf`, a `log_format` of its own: before, nginx's
default line wrote the whole request, with the referer and the user agent). What nginx wrote
before stays in the web container's log until that container is recreated, which the update that
brings this change does. One line nginx still writes in full is its error log, when it cannot
reach the backend: it names the request as it came and the upstream address it tried, query
included in both (seen 2026-10-01 with the backend stopped), and that cannot be configured away.

**Size limit.** Docker keeps a container's log without a limit unless told otherwise, and these
hold operators' account numbers and the addresses they came from. `deploy/docker-compose.yml`
therefore gives `backend` and `web` the last 5 files of 10 MB each, and the NAS's own compose file
has the same since 2026-10-01 (`docker inspect` on both containers shows
`{"Type":"json-file","Config":{"max-file":"5","max-size":"10m"}}`). The NAS runs its own copy of the
file, not the repository's, so a change to the template reaches it only when someone copies it
there. For any other copy of the file (a new NAS), add to the `backend` **and the `web`** service
and recreate the containers:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
```

How long 50 MB of each lasts depends on what is written (an import makes the backend log a good
deal); not yet measured.

**Trying the nginx file.** `frontend/nginx.conf` is the one file whose mistake only nginx catches,
and a mistake would stop the web container from starting. Before publishing a change to it, from
the project's root, with Docker running (PowerShell):

`docker run --rm --add-host backend:127.0.0.1 -v "${PWD}/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1-alpine nginx -t`

must end with `syntax is ok` and `test is successful`. `--add-host` is needed: the file names the
host `backend`, which exists only inside the compose application, and without it `nginx -t` fails
with `host not found in upstream "backend"` whatever else is right. `backend/tests/test_nginx_conf.py`
checks only the file's text and the one regular expression, not that nginx accepts it.

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
