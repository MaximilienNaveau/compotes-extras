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
```

`compotes-src` is a read-only `/nix/store` path (it's fetched, not a live
checkout), so `process-compose.yaml` redirects the sqlite DB to a writable
`/tmp/compotes-dev/db.sqlite3` — this is a run-it-as-deployed loop, not a
live-edit-`compotes`-and-reload one (for that, just run `compotes`'s own
`poetry install`/`manage.py runserver` directly in its own checkout).

### Start

```sh
nix develop -c process-compose up            # foreground, with the TUI
nix develop -c process-compose up -D         # detached - returns immediately
```

Runs `migrate` then `runserver`. Browse to `http://compotes.localhost:8000/`
(`settings.py`'s `ALLOWED_HOSTS` doesn't accept plain `localhost`). There's no
initial user — create one once, the first time, against the same DB path:

```sh
nix develop -c bash -c '
  cd "$COMPOTES_SRC"
  DB=/tmp/compotes-dev/db.sqlite3 \
  DJANGO_SUPERUSER_USERNAME=dev DJANGO_SUPERUSER_EMAIL=dev@example.org \
  DJANGO_SUPERUSER_PASSWORD=devdevdev \
  python manage.py createsuperuser --noinput
'
```

### Stop

```sh
nix develop -c process-compose down
```

Works from any terminal (detached or not) — `process-compose` tracks the
running project via a local port, not the shell session that started it.

### Update (keeping the same data)

To pick up a newer `extras-base` commit — e.g. after a fix like the French
translations in this session — without losing what's in the dev DB:

```sh
nix develop -c process-compose down     # stop the old build's processes
nix flake update compotes-src           # re-pin to extras-base's current tip
nix develop -c process-compose up       # rebuilds as needed, starts fresh
```

The sqlite file lives at the fixed path `/tmp/compotes-dev/db.sqlite3`,
outside the Nix store, so it's untouched by any of this — only the *code*
changes underneath it. `migrate` re-runs on every start but is a no-op
unless the update actually added new migrations. Verified: created an event,
went through a full down → update → up cycle, the event was still there
afterward.

To start over with a blank DB instead, delete it first:
`rm -rf /tmp/compotes-dev`.

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
