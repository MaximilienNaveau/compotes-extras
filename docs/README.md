# compotes-extras implementation docs

The REST API half of the walkthrough that starts in compotes' own
[docs/](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/README.md)
(01-django-concepts, 02-data-model-and-math, 05-docker-deployment). These
two live here instead, since they're specifically about what this repo
adds on top of compotes, not compotes itself:

1. [03-rest-api.md](03-rest-api.md) — the JSON API: what Django REST
   Framework is, every endpoint, and a real bug it caught before you saw it.
2. [04-auth-and-security.md](04-auth-and-security.md) — tokens vs sessions,
   rate limiting, HTTPS settings, and the trust model this app deliberately
   accepts.

Every claim points at exact files/line numbers and, where possible, a test
that proves it — re-derive things yourself rather than taking the prose's
word for it:

```bash
# from packages/rest_api/
poetry install --with dev
poetry run python manage.py test  # 8 tests should pass
```
