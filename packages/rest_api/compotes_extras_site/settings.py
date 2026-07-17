"""Full-stack settings: compotes' own settings, extended with the REST API.

compotes itself carries none of this - it stays a clean, upstream-mergeable
fork. This is where "run the whole stack" (plus the production hardening
that goes with exposing it) lives instead.
"""

from compotes.settings import *  # noqa: F403

INSTALLED_APPS = [
    *INSTALLED_APPS,  # noqa: F405
    "compotes_rest_api",
    "rest_framework",
    "rest_framework.authtoken",
]

ROOT_URLCONF = "compotes_extras_site.urls"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "120/min",
        # Tighter, dedicated scope for /api/token/ to slow password guessing.
        "login": "5/min",
    },
}

if not DEBUG:  # noqa: F405
    # Traefik terminates TLS and proxies to gunicorn over plain HTTP.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
