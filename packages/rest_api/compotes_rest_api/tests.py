"""Tests for the compotes API."""

from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from compotes.models import Debt, Event, Part, Pool, User
from compotes_rest_api.views import LoginRateThrottle


class ApiTests(APITestCase):
    """Test the API endpoints."""

    def setUp(self):
        """Create a few users, and start with a clean throttle cache.

        LocMemCache persists across TestCase classes within a test run
        (only the DB is transaction-rolled-back), so without this, login
        attempts from other tests could trip the real login throttle here.
        """
        cache.clear()
        for guy in "abcd":
            User.objects.create_user(guy, email=f"{guy}@example.org", password=guy)
        self.user = User.objects.get(username="a")

    def authenticate(self):
        """Obtain a token for self.user, and use it for the client."""
        response = self.client.post(
            reverse("compotes_rest_api:token"),
            {"username": "a", "password": "a"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def test_requires_auth(self):
        """Anonymous requests are rejected."""
        response = self.client.get(reverse("compotes_rest_api:user-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me(self):
        """The me action returns the requesting user."""
        self.authenticate()
        response = self.client.get(reverse("compotes_rest_api:user-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "a")

    def test_debt_and_part_flow(self):
        """Creating a Debt and Parts through the API updates balances."""
        self.authenticate()
        response = self.client.post(
            reverse("compotes_rest_api:debt-list"),
            {
                "name": "debt 1",
                "date": "2026-07-03T00:00:00Z",
                "creditor": self.user.pk,
                "value": "100.03",
                "description": "",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        debt_pk = response.data["id"]

        for user in User.objects.all():
            response = self.client.post(
                reverse("compotes_rest_api:part-list"),
                {"debt": debt_pk, "debitor": user.pk, "part": 25},
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        debt = Debt.objects.get(pk=debt_pk)
        self.assertEqual(debt.part_value, 1.0003)
        self.assertEqual(User.objects.get(username="a").balance, Decimal("75.02"))
        self.assertEqual(User.objects.get(username="d").balance, Decimal("-25.01"))

    def test_part_delete_updates_balance(self):
        """Deleting a Part recomputes the Debt & Debitor balances."""
        self.authenticate()
        debt = Debt.objects.create(creditor=self.user, value=100, name="debt 1")
        parts = [
            Part.objects.create(debt=debt, debitor=user, part=1)
            for user in User.objects.all()
        ]
        self.assertEqual(User.objects.get(username="d").balance, Decimal("-25"))

        response = self.client.delete(
            reverse("compotes_rest_api:part-detail", args=[parts[-1].pk]),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(User.objects.get(username="d").balance, Decimal("0"))

    def test_logout_revokes_token(self):
        """Logging out deletes the token, invalidating every device using it."""
        self.authenticate()
        response = self.client.post(reverse("compotes_rest_api:logout"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(reverse("compotes_rest_api:user-me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pool_and_share_flow(self):
        """Creating a Pool and setting a Share through the API works."""
        self.authenticate()
        response = self.client.post(
            reverse("compotes_rest_api:pool-list"),
            {"name": "pool 1", "description": "", "value": "90"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pool = Pool.objects.get(pk=response.data["id"])
        self.assertEqual(pool.organiser, self.user)

        response = self.client.post(
            reverse("compotes_rest_api:token"),
            {"username": "b", "password": "b"},
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")

        response = self.client.put(
            reverse("compotes_rest_api:pool-share", args=[pool.slug]),
            {"maxi": "100"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pool.refresh_from_db()
        self.assertEqual(pool.ratio, 0.9)
        self.assertEqual(User.objects.get(username="a").balance, Decimal("90"))
        self.assertEqual(User.objects.get(username="b").balance, Decimal("-90"))


class ApiEventTests(APITestCase):
    """Test the Event API: isolation, close confirmation, and reopen."""

    def setUp(self):
        """Create two users, and authenticate as the first one."""
        cache.clear()
        for guy in "ab":
            User.objects.create_user(guy, email=f"{guy}@example.org", password=guy)
        self.user = User.objects.get(username="a")
        response = self.client.post(
            reverse("compotes_rest_api:token"),
            {"username": "a", "password": "a"},
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")

    def test_event_debt_isolation_close_and_reopen(self):
        """A Debt scoped to an Event is isolated until the Event is closed."""
        response = self.client.post(
            reverse("compotes_rest_api:event-list"),
            {"name": "trip", "description": ""},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event_id = response.data["id"]
        event_slug = response.data["slug"]
        self.assertEqual(Event.objects.get(pk=event_id).organiser, self.user)

        b = User.objects.get(username="b")
        response = self.client.post(
            reverse("compotes_rest_api:debt-list"),
            {
                "name": "hotel",
                "date": "2026-07-04T00:00:00Z",
                "creditor": self.user.pk,
                "event": event_id,
                "value": "100",
                "description": "",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.post(
            reverse("compotes_rest_api:part-list"),
            {"debt": response.data["id"], "debitor": b.pk, "part": 1},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Isolated: global balances untouched while the Event is open.
        self.assertEqual(User.objects.get(username="a").balance, Decimal("0"))
        self.assertEqual(User.objects.get(username="b").balance, Decimal("0"))

        response = self.client.get(
            reverse("compotes_rest_api:event-balances", args=[event_slug]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balances = {row["user"]["username"]: row["balance"] for row in response.data}
        self.assertEqual(balances["a"], 100)
        self.assertEqual(balances["b"], -100)

        # Closing without confirmation is refused.
        response = self.client.post(
            reverse("compotes_rest_api:event-close", args=[event_slug]),
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(User.objects.get(username="a").balance, Decimal("0"))

        # Closing with confirmation folds it into the global balance.
        response = self.client.post(
            reverse("compotes_rest_api:event-close", args=[event_slug]),
            {"confirm": "true"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.get(username="a").balance, Decimal("100"))
        self.assertEqual(User.objects.get(username="b").balance, Decimal("-100"))

        # Reopening isolates it again.
        response = self.client.post(
            reverse("compotes_rest_api:event-reopen", args=[event_slug]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.get(username="a").balance, Decimal("0"))
        self.assertEqual(User.objects.get(username="b").balance, Decimal("0"))


class ApiThrottleTests(APITestCase):
    """Test that login attempts are throttled against password guessing."""

    def setUp(self):
        """Create a user, and start with a clean throttle cache."""
        User.objects.create_user("a", email="a@example.org", password="a")
        cache.clear()

    def test_login_is_throttled(self):
        """A second login attempt within the throttle window is rejected.

        THROTTLE_RATES is snapshotted onto the throttle class at import
        time, so override_settings(REST_FRAMEWORK=...) can't reach it here;
        patch the class attribute directly instead.
        """
        with mock.patch.object(LoginRateThrottle, "THROTTLE_RATES", {"login": "1/min"}):
            url = reverse("compotes_rest_api:token")
            self.client.post(url, {"username": "a", "password": "wrong"})
            response = self.client.post(url, {"username": "a", "password": "a"})
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
