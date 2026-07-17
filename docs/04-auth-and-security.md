# Authentication, security settings, and the trust model

## Two ways to authenticate

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    ...
}
```
([compotes_extras_site/settings.py:19-40](../packages/rest_api/compotes_extras_site/settings.py#L19-L40))

- **SessionAuthentication** is what the *web app* uses: log in via
  `/accounts/login/` (a Django built-in view), get a session cookie, every
  subsequent request's cookie identifies you. This is why
  `EventViewSet`/`LogoutView` are reachable from a plain logged-in browser
  tab too, not just from a mobile client with a token.
- **TokenAuthentication** is what a mobile client (or any non-browser
  client) uses instead of cookies: a random opaque string, stored one-per-user
  in a database table (`rest_framework.authtoken`'s `Token` model, added to
  `INSTALLED_APPS` alongside `compotes_rest_api`), sent on every request as
  an `Authorization: Token <key>` header. There's no expiry baked into DRF's
  implementation — a token is valid until explicitly deleted.

Both are listed, and DRF tries each in order per request — a browser session
cookie *or* a bearer token both work against the exact same endpoints.

### Login

```python
class LoginView(ObtainAuthToken):
    throttle_classes = [LoginRateThrottle]
```
(`compotes_rest_api/views.py`) — `ObtainAuthToken` is DRF's built-in "trade credentials for
a token" view: it validates `username`+`password` against Django's
configured auth backends and returns `{"token": "<key>"}`
(`Token.objects.get_or_create(user=user)` — the *same* token every time you
log in from the same account, not a fresh one). The custom
`AUTHENTICATION_BACKENDS` setting:

```python
AUTHENTICATION_BACKENDS = ["yeouia.backends.YummyEmailOrUsernameInsensitiveAuth"]
```
(compotes' own [settings.py:146](https://github.com/MaximilienNaveau/compotes/blob/extras-base/compotes/settings.py#L146),
inherited as-is — not something compotes-extras adds) — a third-party
backend that lets `username` in that login request be *either* the actual
username or the email address, case-insensitively. This project didn't need
to write any of that logic — worth knowing it's there so "why does logging
in with an email work" isn't a mystery later.

### Logout and the lost-phone problem

```python
class LogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

Because there is exactly **one** token per user (not one per device), this
single delete revokes access for *every* device that user is logged into,
not just the one making the request. That's a deliberate trade-off: it's
simpler to reason about and implement than a per-device token table, and it
turns "I lost my phone" into "log into the website from any other device and
hit logout" — an easy panic button precisely because it's blunt. The cost is
you can't log out *just* the lost phone while staying logged in elsewhere;
every device has to log back in. If this app ever needed finer-grained
per-device sessions, that would mean replacing DRF's built-in `Token` model
with a custom one keyed by `(user, device)` instead of just `user` — a real
change, not a config flag, so it's listed here as a known limitation rather
than something already handled.

## Throttling — and two real gotchas found while building it

Throttling means rate-limiting: rejecting a request with `429 Too Many
Requests` once a client (identified by IP if anonymous, by user ID if
authenticated) exceeds a configured rate.

```python
"DEFAULT_THROTTLE_CLASSES": [
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
],
"DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "120/min", "login": "5/min"},
```

**Gotcha 1 — DRF's own login view opts itself out of your global config.**
`rest_framework.authtoken.views.ObtainAuthToken` hardcodes
`throttle_classes = ()` in its source. That means setting
`DEFAULT_THROTTLE_CLASSES` project-wide does **not** protect `/api/token/` —
the exact endpoint a password-guessing attack would target. This was only
caught by writing a test for it and watching it fail (login succeeded on
attempt #2, when it should have been throttled). The fix is a dedicated
throttle class assigned directly on a thin subclass:

```python
class LoginRateThrottle(AnonRateThrottle):
    scope = "login"

class LoginView(ObtainAuthToken):
    throttle_classes = [LoginRateThrottle]
```

The lesson: **never assume a third-party class respects your global
settings — check its source, or better, write a test that actually exercises
the behavior you're relying on.** A security control you believe is active
but isn't is worse than no control, because it creates false confidence.

**Gotcha 2 — `THROTTLE_RATES` is a class attribute, frozen at import time.**
`SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES` is
evaluated once, when `rest_framework.throttling` is first imported — *not*
re-read on every request. This means Django's usual test tool for
temporarily changing a setting, `override_settings(REST_FRAMEWORK={...})`,
has no effect on throttle rates in tests, because the dictionary was already
copied onto the class before the override ever runs. [compotes_rest_api/tests.py](../packages/rest_api/compotes_rest_api/tests.py)'s
`ApiThrottleTests` works around it with `mock.patch.object` on the throttle
class directly instead:

```python
with mock.patch.object(LoginRateThrottle, "THROTTLE_RATES", {"login": "1/min"}):
    ...
```

This is a Django/DRF quirk worth remembering any time a setting seems to
have "no effect" in a test — check whether the library copied it onto a
class attribute at import time instead of reading `settings` fresh each
time.

**A related test-isolation trap:** DRF's throttle cache uses Django's
default cache backend (`LocMemCache`), which persists for the whole test
*process*, unlike the database (which Django wraps in a transaction per test
and rolls back). Without an explicit `cache.clear()` in `setUp`, login
attempts from an earlier test class can silently count against a later
test's throttle budget and make it fail — this actually happened once while
building this feature (see the `cache.clear()` calls throughout
[compotes_rest_api/tests.py](../packages/rest_api/compotes_rest_api/tests.py)'s
`setUp` methods).

## Permission model: who's allowed to do what

```python
"DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
```

This is the *only* authorization rule applied globally: you must be logged
in, full stop. There is **no ownership check** anywhere — any authenticated
user can update or delete *any* Debt, Pool, or Event, not just ones they
created. This mirrors the original web app's behavior exactly (its
`DebtUpdateView`/`PoolUpdateView` never check `request.user` against
`creditor`/`organiser` either — see `test_views` in compotes'
[tests.py](https://github.com/MaximilienNaveau/compotes/blob/extras-base/compotes/tests.py),
which explicitly asserts that a *different* user can edit someone else's
Debt/Pool).

This is a deliberate design for a small trusted group (the app's own
`README.md` describes it as "track debts & pools" for people who already
trust each other with money), not an oversight — but it's the single most
important thing to be upfront about with a reviewer, because it's the kind
of thing that looks like a bug if you don't say out loud that it's
intentional. **The one thing this design assumes and requires: never give an
account to someone you wouldn't trust to edit any entry in the whole
system.** If that assumption ever needs to change (e.g. a "family" instance
growing to include a landlord, or several unrelated households sharing one
server), ownership checks would need to be added explicitly — they don't
fall out of anything already here.

## HTTPS, HSTS, and cookies

```python
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
```
([compotes_extras_site/settings.py:42-50](../packages/rest_api/compotes_extras_site/settings.py#L42-L50))

- `SECURE_SSL_REDIRECT` — Django itself 301-redirects any plain-HTTP request
  to HTTPS.
- `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` — tell the browser to never
  send these cookies over an unencrypted connection, even if somehow asked
  to (defense in depth beyond the redirect above).
- `SECURE_HSTS_SECONDS` (and its two companion flags) — sends a
  `Strict-Transport-Security` header telling the browser "for the next year,
  don't even *try* plain HTTP for this domain (or its subdomains), go
  straight to HTTPS" — this protects the *first* request too, which a
  redirect alone can't (a redirect still requires one initial insecure
  round-trip).
- `SECURE_PROXY_SSL_HEADER` exists because of how this app is actually
  deployed (see compotes'
  [05-docker-deployment.md](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/05-docker-deployment.md)):
  Traefik terminates TLS at the edge and forwards plain HTTP to the app container.
  Without telling Django to trust the `X-Forwarded-Proto` header set by that
  proxy, Django would think *every* request is insecure (since it never
  sees HTTPS directly) and either loop redirecting forever or treat
  everything as insecure. **This setting is only safe because the app
  container is not directly reachable from the internet** — only Traefik is
  — otherwise an attacker could forge that header themselves and bypass the
  HTTPS requirement.

All of this only activates when `DEBUG=False`, i.e. in production — local
development still runs over plain `http://localhost` without needing a
certificate.

## Password strength

```python
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"{_APV}.UserAttributeSimilarityValidator"},  # rejects passwords too similar to your username/email/name
    {"NAME": f"{_APV}.MinimumLengthValidator"},             # default: at least 8 characters
    {"NAME": f"{_APV}.CommonPasswordValidator"},            # rejects ~20,000 known common passwords
    {"NAME": f"{_APV}.NumericPasswordValidator"},           # rejects all-digit passwords
]
```
These are Django's own built-in validators, applied whenever a password is
set via a Django form (registration, password change) — not bypassable from
the web UI. They do **not** apply retroactively to already-existing
passwords, only at the moment a password is set or changed.

## Self-check

```bash
# from packages/rest_api/
poetry run python manage.py test compotes_rest_api.tests.ApiThrottleTests -v2  # proves the login throttle fires
```

Try it by hand too, against a running instance (see the root README): log
in with a wrong password 6 times in under a minute against `/api/token/` —
the 6th should come back `429`, not `400`.

Next: compotes'
[05-docker-deployment.md](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/05-docker-deployment.md)
covers how the whole stack actually gets deployed, including exactly where
that Traefik proxy above lives.
