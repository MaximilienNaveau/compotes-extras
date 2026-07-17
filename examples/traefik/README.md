# Nix + Traefik, no Docker

For a real prod environment where Nix and Traefik already exist (the goal
this example is actually for), you don't need anything Docker-specific —
`compotes` runs as a plain gunicorn process via Nix, and Traefik picks it
up the same way it picks up any other backend: a small **file provider**
config (`dynamic.yml`), instead of the Docker-provider labels
`docker-compose.yml` uses.

## Files

- `process-compose.yaml` — `migrate` → `gunicorn` (bound to `127.0.0.1`,
  not `0.0.0.0` — the app has no public port of its own, same as `app` in
  `docker-compose.yml`) → `traefik` (only for local testing, see below).
- `traefik.yml` — Traefik's static config: one entrypoint (`:8090`), file
  provider pointed at `dynamic.yml`.
- `dynamic.yml` — the actual routing rule: `` Host(`compotes.localhost`) ``
  → `http://127.0.0.1:8000`. Same `Host()` shape as
  `docker-compose.yml`'s `traefik.http.routers.compotes-app.rule` label,
  and matches `settings.py`'s own `ALLOWED_HOSTS` default
  (`f"{PROJECT}.{DOMAIN_NAME}"`) — no extra `ALLOWED_HOST` config needed.

## Testing it locally (spins up its own throwaway Traefik)

```sh
nix develop ../..#prod        # gunicorn + process-compose + traefik on PATH
process-compose up -D
curl -H "Host: compotes.localhost" http://127.0.0.1:8090/   # -> 302 to login
curl -H "Host: wrong.localhost"     http://127.0.0.1:8090/   # -> 404, proves Host() actually matters
process-compose down
```

## Deploying for real (Traefik already running elsewhere)

Skip the `traefik` process entirely — you don't need a second one:

```sh
process-compose up migrate gunicorn -D
```

Then copy `dynamic.yml` (adjusted for your actual domain — swap
`compotes.localhost` for the real one, and the port if you changed
`APP_PORT`) into whatever directory *your* Traefik's own file provider
already watches. If your Traefik doesn't have one yet, that's one line in
its static config:

```yaml
providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true
```

No labels, no Docker socket, no `docker-compose.yml` — just a file.

## Known gap

Gunicorn never serves `/static` or `/media` itself, unlike
`manage.py runserver` under `DEBUG=True` (what the main dev
loop — `../../process-compose.yaml` — uses instead). This example doesn't
solve that (no nginx, no whitenoise) — CSS/JS will 404 until something
does. See the root [`.env.example`](../../.env.example)'s note on `DEBUG`
for the full explanation.

## Config

Same variables as [`../../.env.example`](../../.env.example)
(`CHATONS_ROOT_DIR`, `APP_NAME`, `DB`/`POSTGRES_*`, `SECRET_KEY`, ...), plus
`APP_PORT` (gunicorn's bind port, default `8000` — keep `dynamic.yml`'s
backend URL in sync if you change it). Drop a `.env` in this directory to
set them; `process-compose` loads it automatically.
