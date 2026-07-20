# Docker Compose, no Nix

For a server that doesn't have Nix yet: a straight copy of compotes' own
[`docker-compose.yml`](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docker-compose.yml)
+ [`Dockerfile`](https://github.com/MaximilienNaveau/compotes/blob/extras-base/Dockerfile),
pointed at this repo's app instead of a plain `compotes` checkout - same
Postgres + nginx + Traefik-via-Docker-labels shape, same `/srv/compotes/*`
host paths, same container names. This is a drop-in replacement for
compotes' own `docker-compose.yml`, not something meant to run alongside
it.

[`../prod/`](../prod) (Nix + Traefik's file provider) is still the intended
long-term path once Nix is available on the server - keep both in mind if
`compotes_extras_site` or its dependencies change, so this one doesn't
silently bit-rot.

## What's actually different from compotes' own docker-compose.yml

- **Build context is the repo root**, not this directory -
  [`./Dockerfile`](Dockerfile)'s `ADD`s pull from `packages/rest_api/`
  instead of a repo root that's just `compotes/`.
- **`DJANGO_SETTINGS_MODULE=compotes_extras_site.settings`**, baked in via
  the Dockerfile's `ENV` (not just passed to one command), so `migrate`,
  `collectstatic`, `gunicorn`, and `docker exec compotes-app-1 poetry run
  ./manage.py reminder` (the weekly reminder timer, below) all get the
  REST-enabled settings/urls without repeating `--settings` everywhere.
  `compotes.wsgi`'s own `os.environ.setdefault(...)` means `compotes.wsgi`
  itself doesn't need to change - see the root
  [`README.md`](../README.md)'s "How the full stack gets assembled".
- **`name: compotes`** pins the Compose project name (so container names
  stay `compotes-app-1`/`compotes-postgres-1`/`compotes-nginx-1`) since
  this file lives in a `docker/` subdirectory, not a repo checkout that's
  itself called `compotes` the way Compose's directory-name default
  assumes.
- **Two-stage `poetry install`** in the Dockerfile: the second one (no
  `--no-root`) actually installs `compotes_extras_site`/`compotes_rest_api`
  as packages, unlike compotes' own bare `compotes/` directory, which is
  never pip-installed and only works via `manage.py`'s CWD. Skipping this
  is the same `mkPoetryEnv`-vs-`mkPoetryApplication` mistake `flake.nix`'s
  comments describe, just on the Docker side.

Everything else - Postgres, the nginx sidecar serving `/static`/`/media`,
Traefik picking `app` up via Docker labels - is an unmodified copy.

## Deploying

```sh
docker network create web   # if it doesn't already exist - Traefik must be watching it
cp .env.example .env && "$EDITOR" .env   # DOMAIN_NAME, POSTGRES_PASSWORD, SECRET_KEY at minimum
docker compose up -d --build
```

Unlike [`../prod/`](../prod)'s gunicorn (no nginx/whitenoise in front of
it - see its "Known gap"), this one really does serve `/static`/`/media`
once `DEBUG=False`, so there's no reason to hold off on that here - see
[`.env.example`](.env.example).

Weekly reminder email, same as compotes' own `conf/`:

```sh
sudo cp conf/compotes.service conf/compotes.timer /etc/systemd/system/
sudo systemctl enable --now compotes.timer
```

## Config

Same variables as [`../.env.example`](../.env.example) /
[`../prod/.env.example`](../prod/.env.example) where they overlap
(`CHATONS_ROOT_DIR`, `DB`/`POSTGRES_*`, `SECRET_KEY`, `DEBUG`), plus
`DOMAIN_NAME` (used directly in the Traefik router rule labels, unlike
`../prod/`'s `dynamic.yml` which needs hand-editing for a real domain).
Copy [`.env.example`](.env.example) to `.env` in this directory and edit -
`docker compose` loads it automatically, same as compotes' own
`docker-compose.yml`.
