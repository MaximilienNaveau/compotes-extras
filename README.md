# compotes-extras

REST API and client tooling for [compotes](https://github.com/nim65s/compotes),
kept separate from the upstream project since it isn't something the
upstream maintainer wants to carry.

## Packages

- [`packages/rest_api`](packages/rest_api) — `compotes-rest-api`, the Django
  REST Framework app (extracted from what was originally an in-tree `api`
  app on [MaximilienNaveau/compotes](https://github.com/MaximilienNaveau/compotes)).
  Depends on `compotes` (and its `actions` app) as an external package. See
  its own README / [compotes' docs/03-rest-api.md](https://github.com/MaximilienNaveau/compotes/blob/main/docs/03-rest-api.md)
  for the endpoint reference.
- [`packages/rest_client`](packages/rest_client) — `compotes-rest-client`, a
  thin Python client wrapping that API with `requests`. No dependency on
  Django or the API package itself.

A GUI package may be added later as a sibling under `packages/`.

## Nix packaging & local dev instance

The root `flake.nix` is the shared foundation for running the full stack
(compotes + compotes-rest-api) via Nix — for local dev now, and later as a
base for a NixOS module or a Docker image. It lives here rather than on
`compotes` deliberately: `compotes` stays a clean, upstream-mergeable fork
(just the events feature), with zero Nix files of its own. `flake.nix`
fetches it via the `compotes-src` input (pinned in `flake.lock`, bump with
`nix flake update compotes-src`) and combines it with this repo's own
`compotes-rest-api`, using [poetry2nix](https://github.com/nix-community/poetry2nix).

```sh
nix build            # packages.default: the full app as an installable Nix package
nix develop           # devShell: python/poetry/process-compose, $COMPOTES_SRC set
nix develop -c process-compose up   # migrate + runserver, sqlite, http://compotes.localhost:8000/
```

`compotes-src` is a read-only `/nix/store` path (it's fetched, not a live
checkout), so `process-compose.yaml` redirects the sqlite DB to a writable
`/tmp/compotes-dev/db.sqlite3` — this is a run-it-as-deployed loop, not a
live-edit-`compotes`-and-reload one (for that, just run `compotes`'s own
`poetry install`/`manage.py runserver` directly in its own checkout).

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
