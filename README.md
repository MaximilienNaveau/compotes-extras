# compotes-extras

REST API and client tooling for [compotes](https://github.com/nim65s/compotes),
kept separate from the upstream project since it isn't something the
upstream maintainer wants to carry. `compotes` depends on nothing here —
it's the other way around: this repo depends on `compotes`, assembles the
full stack (HTML + REST), and is the one place that actually runs it.

## Packages

- [`packages/rest_api`](packages/rest_api) — `compotes-rest-api`: the
  Django REST Framework app itself (`compotes_rest_api/`, extracted from
  what was originally an in-tree `api` app on
  [MaximilienNaveau/compotes](https://github.com/MaximilienNaveau/compotes)),
  plus `compotes_extras_site/` — the settings/urls module that wires
  `compotes_rest_api` into `compotes` from the outside (see "How the full
  stack gets assembled" below) and the prod-server dependencies
  (`gunicorn`, `psycopg2`) needed to actually run it. See its own
  [docs/03-rest-api.md](docs/03-rest-api.md) /
  [docs/04-auth-and-security.md](docs/04-auth-and-security.md) for the
  endpoint reference.
- [`packages/rest_client`](packages/rest_client) — `compotes-rest-client`, a
  thin Python client wrapping that API with `requests`. No dependency on
  Django or the API package itself.

A GUI package may be added later as a sibling under `packages/`.

## `compotes`' branches

[MaximilienNaveau/compotes](https://github.com/MaximilienNaveau/compotes) has
three relevant branches, none of which know anything about REST or Nix:

- `main` — a pristine mirror of `nim65s/main` (upstream), zero diff. Nothing
  fork-specific lives here.
- `events-upstream` — `nim65s/main` + the events feature + its French
  translations, nothing else. This is the PR branch proposed upstream, kept
  minimal on purpose (see [compotes' `docs/README.md`](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/README.md)
  for why: the maintainer doesn't want AI-heavy or overly complex PRs).
- `docs-upstream` — `events-upstream` + implementation docs (Django
  concepts, the data model/math, deployment) proposed as a separate PR.
- `extras-base` — `events-upstream` + one tiny packaging fix (ships the
  `actions` app in the built wheel; poetry-core's default package
  auto-detection otherwise only picks up `compotes/`). **This is what
  `packages/rest_api/pyproject.toml` depends on** — the only place
  `compotes` is referenced from this repo, an ordinary git dependency, not
  a special Nix wiring.

## How the full stack gets assembled

`compotes_extras_site` (in `packages/rest_api`) is the whole trick:

```python
# compotes_extras_site/settings.py
from compotes.settings import *
INSTALLED_APPS = [*INSTALLED_APPS, "compotes_rest_api", "rest_framework", "rest_framework.authtoken"]
REST_FRAMEWORK = {...}
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ...  # HSTS/secure-cookie hardening, since Traefik terminates TLS

# compotes_extras_site/urls.py
from compotes.urls import urlpatterns as compotes_urlpatterns
urlpatterns = [*compotes_urlpatterns, path("api/", include("compotes_rest_api.urls"))]
```

Plain Django settings/urls inheritance — `compotes`'s own `settings.py`/
`urls.py` are never touched, just imported and extended. Running
`compotes.wsgi:application` or `manage.py`-equivalent commands with
`DJANGO_SETTINGS_MODULE=compotes_extras_site.settings` (or
`--settings=compotes_extras_site.settings`) gets you the whole stack;
`compotes.wsgi`'s own `os.environ.setdefault(...)` means this works without
touching that file either. Verified directly: both HTML views (`/`,
`/events`) and REST endpoints (`/api/users/me/`, `/api/token/`) respond
correctly through the exact same running process.

## Nix packaging & local dev instance

The root `flake.nix` builds the full stack via
[poetry2nix](https://github.com/nix-community/poetry2nix), with
`packages/rest_api` as the project root — poetry2nix fetches `compotes`
itself (an ordinary git dependency declared in
`packages/rest_api/pyproject.toml`, pinned to `extras-base`'s tip). There's
no flake input for `compotes` and no `$COMPOTES_SRC`: once built, `compotes`
is just another installed Python package.

There are two symmetric recipes, mirroring `compotes`' own dev (plain
`poetry install`, sqlite) vs. prod (`docker-compose.yml`: gunicorn +
Postgres + nginx + Traefik) split:

|                | dev (`nix run .#dev`)         | prod (`nix run .#prod`)                |
|----------------|--------------------------------|------------------------------------------|
| Config         | [`process-compose.yaml`](process-compose.yaml) | [`process-compose.prod.yaml`](process-compose.prod.yaml) |
| App server     | `manage.py`-equivalent `runserver` | `gunicorn` (`devShells.prod`'s env, not the dev one — has gunicorn/psycopg2, no dev tools) |
| Fronted by     | nothing — browse to it directly | Traefik (file provider — see [`prod/README.md`](prod/README.md)) |
| Static/media   | served automatically (`DEBUG=True`) | **not served** — known gap, see `.env.example` |
| Ready-made dir | [`dev/`](dev)                 | [`prod/`](prod)                          |

```sh
nix build             # packages.default: the full app (prod build) as an installable Nix package
nix develop           # devShells.default: dev shell - python/poetry/process-compose
nix develop .#prod    # devShells.prod: prod shell - gunicorn/psycopg2/traefik instead, no dev tools
nix run .#dev         # apps.dev (= apps.default): start the dev instance directly
nix run .#prod        # apps.prod: start the prod instance directly
```

Both process-compose recipes redirect the sqlite DB to a writable
`$CHATONS_ROOT_DIR/compotes/$APP_NAME/db.sqlite3` (defaults to
`/tmp/compotes/dev/db.sqlite3` for dev — same `CHATONS_ROOT_DIR` convention
`compotes`' own `docker-compose.yml` uses, see `.env.example`) — this is a
run-it-as-deployed loop, not a live-edit-`compotes`-and-reload one (for
that, just run `compotes`'s own `poetry install`/`manage.py runserver`
directly in its own checkout — it won't have the REST API, by design).

`nix run` is the idiomatic entrypoint for "spawn a program" (`nix develop -c`
is for entering an interactive shell instead — still there for anything
needing one, e.g. `createsuperuser` below, or `devShells.prod` for
interactive poking in a prod-like env). Both apps wrap `process-compose`,
with everything after `--` passed straight through:

```sh
nix run .#dev                    # foreground, with the TUI (bare process-compose defaults to `up`)
nix run .#dev -- up -D           # detached - returns immediately
nix run .#dev -- down            # stop - works from any directory/terminal, talks to the running instance over its port
```
(same shape for `.#prod`.)

Runs `migrate` then `runserver` (dev) or `gunicorn` (prod). Browse to
`http://compotes.localhost:8000/` (`settings.py`'s `ALLOWED_HOSTS` doesn't
accept plain `localhost`) — through Traefik at `:8090` instead for prod, see
[`prod/README.md`](prod/README.md). There's no signup flow — create a user
once, the first time, against the same DB path:

```sh
nix develop -c bash -c '
  DB=/tmp/compotes/dev/db.sqlite3 \
  DJANGO_SUPERUSER_USERNAME=dev DJANGO_SUPERUSER_EMAIL=dev@example.org \
  DJANGO_SUPERUSER_PASSWORD=devdevdev \
  python -m django createsuperuser --settings=compotes_extras_site.settings --noinput
'
```
(Path matches `dev/.env`'s defaults — adjust if using a different
`APP_NAME`/`CHATONS_ROOT_DIR`, or for `prod/`.)

### Configuring it: `.env`

`process-compose` loads a `.env` file from whatever directory you run it
from automatically — nothing needs to know it exists beyond that. See
[`.env.example`](.env.example) for every variable (port, a name to
namespace the data dir by — so multiple instances don't collide — DB
backend, `SECRET_KEY`, `ALLOWED_HOST`, `CHATONS_ROOT_DIR`, ...). Two
ready-made places to run from, one per recipe:

- [`dev/`](dev) — has a `.env` already, for working on this checkout:
  `cd dev && nix run ..#dev -- up -D`.
- [`prod/`](prod) — the `.#prod` recipe (gunicorn + Traefik), for a real
  deployment where Nix and Traefik already exist, including how to plug
  into a Traefik that's *already running elsewhere*, not just a local demo:
  `cd prod && nix run ..#prod -- up -D`. Both directories work equally well
  pointed at `github:MaximilienNaveau/compotes-extras#dev`/`#prod` instead
  of `..`, for running on a machine that doesn't have this cloned.

(If you're editing either `process-compose*.yaml` file: every `$` in its
commands is doubled (`$$`) on purpose — `process-compose` does its own
docker-compose-style interpolation on command strings *before* bash sees
them, silently replacing anything it doesn't recognize — including bash's
`${VAR:-default}` syntax — with an empty string. `$$` is its escape for a
literal, unprocessed `$`, letting bash do the actual interpretation instead.
Verified this the hard way: without it, `${APP_NAME:-dev}` silently became
`""`, not `"dev"`.)

### Update (keeping the same data)

To pick up a newer `extras-base` commit — e.g. after a fix on that
branch — without losing what's in the DB:

```sh
nix run .#dev -- down                       # stop the old build's processes (or .#prod)
# bump the `compotes = {git = ..., rev = "..."}` line in
# packages/rest_api/pyproject.toml to the new commit, then:
cd packages/rest_api && poetry lock
nix run .#dev -- up -D                       # rebuilds as needed, starts fresh (or .#prod)
```

The sqlite file lives at a fixed path outside the Nix store (see
`CHATONS_ROOT_DIR` above), so it's untouched by any of this — only the
*code* changes underneath it. `migrate` re-runs on every start but is a
no-op unless the update actually added new migrations.

To start over with a blank DB instead, delete it first (`/tmp/compotes/dev`
by default).

## Provenance

`packages/rest_api/compotes_rest_api` started life as commits `05bced6`
(Add rest API), `bb9ffc0` (Secure rest API), and `aaff329` (Add events in
REST api) on the `compotes` fork, then moved here and renamed from
`api`/`APIConfig` to `compotes_rest_api`/`CompotesRestApiConfig` to avoid
colliding with any other third-party `api` module once installed as an
external dependency. `compotes_extras_site` (settings/urls wiring) and the
`prod` dependency group (gunicorn/psycopg2, mirroring `bb9ffc0`'s HTTPS
hardening) are new, replacing what used to be committed directly onto
`compotes`' own `settings.py`/`urls.py`/`pyproject.toml`.

## Development

Each package under `packages/` is an independent Poetry project with its
own lockfile — there's no root Poetry project (Poetry has no first-class
workspace support). Lint/format config for the whole repo lives in the root
`ruff.toml`.

```sh
cd packages/rest_api && poetry install --with dev && poetry run python manage.py test
cd packages/rest_client && poetry install --with dev && poetry run pytest
```
