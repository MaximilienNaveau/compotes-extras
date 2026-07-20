# Build from the repo root: `docker compose build` (via ./docker-compose.yml's
# `context: ..`), not `docker build .` from this directory - it needs
# packages/rest_api/, not just this file.

FROM python:3.11

EXPOSE 8000

WORKDIR /app

ENV POETRY_VIRTUALENVS_IN_PROJECT=true PYTHONUNBUFFERED=1 PATH=/root/.local/bin:$PATH
# Set here (not just passed to individual commands) so `docker exec
# compotes-app-1 poetry run ./manage.py reminder` (../conf/compotes.service)
# picks up the REST-enabled settings too, without repeating --settings on
# every invocation. manage.py's own os.environ.setdefault(...) only takes
# effect if this isn't already set, so it won't override it.
ENV DJANGO_SETTINGS_MODULE=compotes_extras_site.settings

CMD while ! nc -z postgres 5432; do sleep 1; done \
 && poetry run ./manage.py migrate \
 && poetry run ./manage.py collectstatic --no-input \
 && poetry run gunicorn \
    --bind 0.0.0.0 \
    compotes.wsgi

RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    --mount=type=cache,sharing=locked,target=/root/.cache \
    apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -qqy --no-install-recommends \
    gcc \
    libexpat1 \
    libpq-dev \
    netcat-openbsd \
 && python -m pip install -U pip \
 && python -m pip install pipx \
 && python -m pipx install poetry

# Two stages, same Docker layer-caching trick as compotes' own Dockerfile
# (deps before source, so editing source doesn't invalidate the deps
# layer) - but with a second `poetry install` (no --no-root this time)
# after the source lands: compotes_extras_site/compotes_rest_api are real
# poetry packages (packages/rest_api/pyproject.toml), unlike compotes' own
# bare compotes/ directory, which is never pip-installed and only works via
# manage.py's CWD. Skipping this second install is the same
# mkPoetryEnv-vs-mkPoetryApplication mistake flake.nix's comments describe -
# caught the same way, by actually running the container and hitting
# ModuleNotFoundError: compotes_extras_site.
ADD packages/rest_api/pyproject.toml packages/rest_api/poetry.lock ./
RUN --mount=type=cache,sharing=locked,target=/root/.cache \
    poetry install --with prod --no-root --no-interaction --no-ansi

ADD packages/rest_api .
RUN --mount=type=cache,sharing=locked,target=/root/.cache \
    poetry install --with prod --no-interaction --no-ansi
