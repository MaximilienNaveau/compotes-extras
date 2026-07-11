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
