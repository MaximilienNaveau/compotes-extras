# compotes-extras

REST API and client tooling for [compotes](https://github.com/nim65s/compotes),
kept separate from the upstream project since it isn't something the
upstream maintainer wants to carry.

## Packages

- [`packages/rest_api`](packages/rest_api) — `compotes-rest-api`, the Django
  REST Framework app (extracted from what was originally an in-tree `api`
  app on [MaximilienNaveau/compotes](https://github.com/MaximilienNaveau/compotes)).
  Depends on `compotes` (and its `actions` app) as an external package. See
  its own README / [compotes' docs/03-rest-api.md on the `extras-base` branch](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/03-rest-api.md)
  for the endpoint reference — `compotes`' `main` is a pristine mirror of
  upstream and doesn't carry this doc (see "Branches" below).
- [`packages/rest_client`](packages/rest_client) — `compotes-rest-client`, a
  thin Python client wrapping that API with `requests`. No dependency on
  Django or the API package itself.

A GUI package may be added later as a sibling under `packages/`.

## `compotes`' branches

[MaximilienNaveau/compotes](https://github.com/MaximilienNaveau/compotes) has
two relevant branches:

- `main` — a pristine mirror of `nim65s/main` (upstream), zero diff. Nothing
  fork-specific lives here.
- `events-upstream` — `nim65s/main` + one commit adding the events feature,
  nothing else. This is the PR branch proposed upstream, kept minimal and
  Nix/REST-free on purpose (see [compotes' `docs/README.md`](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/README.md)
  for why: the maintainer doesn't want AI-heavy or overly complex PRs).
- `extras-base` — `events-upstream` + the REST API wiring (`compotes-rest-api`
  in `INSTALLED_APPS`/`urls.py`/`pyproject.toml`) that used to be proposed
  upstream too, before it moved to this repo. **This is what `flake.nix`
  below actually fetches** — not `main`, which doesn't have any of it.

## Nix packaging & local dev instance

The root `flake.nix` is the shared foundation for running the full stack
(compotes + compotes-rest-api) via Nix — for local dev now, and later as a
base for a NixOS module or a Docker image. It lives here rather than on
`compotes` deliberately: `compotes` stays clean and upstream-mergeable, with
zero Nix files of its own. `flake.nix` fetches `compotes`' `extras-base`
branch via the `compotes-src` input (pinned by exact commit in `flake.lock`;
bump with `nix flake update compotes-src` — it'll keep resolving to
`extras-base`'s tip, not `main`, since the input pins the branch ref
explicitly) and combines it with this repo's own `compotes-rest-api`, using
[poetry2nix](https://github.com/nix-community/poetry2nix).

```sh
nix build            # packages.default: the full app as an installable Nix package
nix develop           # devShell: python/poetry/process-compose, $COMPOTES_SRC set
nix run               # apps.default: start the instance directly, see below
```

`compotes-src` is a read-only `/nix/store` path (it's fetched, not a live
checkout), so `process-compose.yaml` redirects the sqlite DB to a writable
`$CHATONS_ROOT_DIR/compotes/$APP_NAME/db.sqlite3` (defaults to
`/tmp/compotes/dev/db.sqlite3` — same `CHATONS_ROOT_DIR` convention
`compotes`' own `docker-compose.yml` uses, see `.env.example`) — this is a
run-it-as-deployed loop, not a live-edit-`compotes`-and-reload one (for
that, just run `compotes`'s own `poetry install`/`manage.py runserver`
directly in its own checkout).

`nix run` is the idiomatic entrypoint for "spawn a program" (`nix develop -c`
is for entering an interactive shell instead — still there for anything
needing one, e.g. `createsuperuser` below). It wraps `process-compose`, with
everything after `--` passed straight through:

```sh
nix run                    # foreground, with the TUI (bare process-compose defaults to `up`)
nix run . -- up -D         # detached - returns immediately
nix run . -- down          # stop - works from any directory/terminal, talks to the running instance over its port
```

Runs `migrate` then `runserver`. Browse to `http://compotes.localhost:8000/`
(`settings.py`'s `ALLOWED_HOSTS` doesn't accept plain `localhost`). There's no
signup flow — create a user once, the first time, against the same DB path:

```sh
nix develop -c bash -c '
  cd "$COMPOTES_SRC"
  DB=/tmp/compotes/dev/db.sqlite3 \
  DJANGO_SUPERUSER_USERNAME=dev DJANGO_SUPERUSER_EMAIL=dev@example.org \
  DJANGO_SUPERUSER_PASSWORD=devdevdev \
  python manage.py createsuperuser --noinput
'
```
(Path matches `dev/.env`'s defaults — adjust if using a different
`APP_NAME`/`CHATONS_ROOT_DIR`.)

### Configuring it: `.env`

`process-compose` loads a `.env` file from whatever directory you run it
from automatically — nothing needs to know it exists beyond that. See
[`.env.example`](.env.example) for every variable (port, a name to
namespace the data dir by — so multiple instances don't collide — DB
backend, `SECRET_KEY`, `ALLOWED_HOST`, `CHATONS_ROOT_DIR`, ...). Note there's
no nginx here, unlike `compotes`' own `docker-compose.yml` — intentional
while `DEBUG=True` (`manage.py runserver` serves static/media files itself
then), but read `.env.example`'s note on `DEBUG` before turning it off, or
CSS/JS will silently 404. Two ready-made places to run from:

- [`dev/`](dev) — has a `.env` already, for working on this checkout:
  `cd dev && nix run .. -- up -D`.
- [`examples/`](examples) — no local checkout, no local flake even: shows
  the same recipe pointed at `github:MaximilienNaveau/compotes-extras`
  directly, for deploying this somewhere else entirely.

(If you're editing `process-compose.yaml` itself: every `$` in its commands
is doubled (`$$`) on purpose — `process-compose` does its own
docker-compose-style interpolation on command strings *before* bash sees
them, silently replacing anything it doesn't recognize — including bash's
`${VAR:-default}` syntax — with an empty string. `$$` is its escape for a
literal, unprocessed `$`, letting bash do the actual interpretation instead.
Verified this the hard way: without it, `${APP_NAME:-dev}` silently became
`""`, not `"dev"`.)

### Update (keeping the same data)

To pick up a newer `extras-base` commit — e.g. after a fix like the French
translations in this session — without losing what's in the DB:

```sh
nix run . -- down       # stop the old build's processes
nix flake update compotes-src           # re-pin to extras-base's current tip
nix run . -- up -D      # rebuilds as needed, starts fresh
```

The sqlite file lives at a fixed path outside the Nix store (see
`CHATONS_ROOT_DIR` above), so it's untouched by any of this — only the
*code* changes underneath it. `migrate` re-runs on every start but is a
no-op unless the update actually added new migrations. Verified: created an
event, went through a full down → update → up cycle, the event was still
there afterward.

To start over with a blank DB instead, delete it first (`/tmp/compotes/dev`
by default).

## Provenance

`packages/rest_api` started life as commits `05bced6` (Add rest API),
`bb9ffc0` (Secure rest API), and `aaff329` (Add events in REST api) on the
`compotes` fork, then moved here and renamed from `api`/`APIConfig` to
`compotes_rest_api`/`CompotesRestApiConfig` to avoid colliding with any
other third-party `api` module once installed as an external dependency.

## Development

Each package under `packages/` is an independent Poetry project with its
own lockfile — there's no root Poetry project (Poetry has no first-class
workspace support). Lint/format config for the whole repo lives in the root
`ruff.toml`.

```sh
cd packages/rest_api && poetry install --with dev && poetry run python manage.py test
cd packages/rest_client && poetry install --with dev && poetry run pytest
```
