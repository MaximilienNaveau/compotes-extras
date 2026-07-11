"""Tests for CompotesClient, mocking HTTP via `responses`."""

import pytest
import requests
import responses

from compotes_rest_client import CompotesClient

BASE_URL = "https://compotes.example.org"


@pytest.fixture
def client():
    """Build a client with no token set yet."""
    return CompotesClient(BASE_URL)


@responses.activate
def test_login_stores_token(client):
    """login() posts credentials and stores the returned token."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/token/",
        json={"token": "abc123"},
        status=200,
    )
    data = client.login("alice", "hunter2")
    assert data == {"token": "abc123"}
    assert client.token == "abc123"
    assert client.session.headers["Authorization"] == "Token abc123"


@responses.activate
def test_logout_clears_token(client):
    """logout() posts to logout/ and drops the stored token."""
    client._set_token("abc123")
    responses.add(responses.POST, f"{BASE_URL}/api/logout/", status=204)
    client.logout()
    assert client.token is None
    assert "Authorization" not in client.session.headers


@responses.activate
def test_get_me(client):
    """get_me() hits users/me/."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/users/me/",
        json={"username": "alice"},
        status=200,
    )
    assert client.get_me() == {"username": "alice"}


@responses.activate
def test_list_events(client):
    """list_events() hits GET events/."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/events/",
        json=[{"slug": "trip"}],
        status=200,
    )
    assert client.list_events() == [{"slug": "trip"}]


@responses.activate
def test_create_event(client):
    """create_event() posts fields to events/."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/events/",
        json={"slug": "trip", "name": "Trip"},
        status=201,
    )
    event = client.create_event(name="Trip", description="")
    assert event["slug"] == "trip"
    assert responses.calls[0].request.body == "name=Trip&description="


@responses.activate
def test_get_event_balances(client):
    """get_event_balances() hits GET events/<slug>/balances/."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/events/trip/balances/",
        json=[{"user": {"username": "a"}, "balance": 100}],
        status=200,
    )
    balances = client.get_event_balances("trip")
    assert balances[0]["balance"] == 100


@responses.activate
def test_close_event_sends_confirm(client):
    """close_event() posts confirm= to events/<slug>/close/."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/events/trip/close/",
        json={"slug": "trip", "closed_at": "2026-07-11T00:00:00Z"},
        status=200,
    )
    event = client.close_event("trip", confirm=True)
    assert event["closed_at"]
    assert responses.calls[0].request.body == "confirm=True"


@responses.activate
def test_reopen_event(client):
    """reopen_event() posts to events/<slug>/reopen/."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/events/trip/reopen/",
        json={"slug": "trip", "closed_at": None},
        status=200,
    )
    event = client.reopen_event("trip")
    assert event["closed_at"] is None


@responses.activate
def test_list_debts_passes_filters(client):
    """list_debts() forwards keyword filters as query params."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/debts/",
        json=[{"id": 1, "name": "hotel"}],
        status=200,
    )
    debts = client.list_debts(user="alice")
    assert debts == [{"id": 1, "name": "hotel"}]
    assert responses.calls[0].request.params == {"user": "alice"}


@responses.activate
def test_create_part(client):
    """create_part() posts fields to parts/."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/api/parts/",
        json={"id": 1, "debt": 1, "debitor": 2, "part": 1},
        status=201,
    )
    part = client.create_part(debt=1, debitor=2, part=1)
    assert part["id"] == 1


@responses.activate
def test_delete_part_returns_none(client):
    """delete_part() returns None on a 204 response."""
    responses.add(responses.DELETE, f"{BASE_URL}/api/parts/1/", status=204)
    assert client.delete_part(1) is None


@responses.activate
def test_pool_share_flow(client):
    """get_share()/update_share() round-trip a Pool's Share."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/pools/trip-pool/share/",
        json={"maxi": None, "value": 0},
        status=200,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/api/pools/trip-pool/share/",
        json={"maxi": "100", "value": 10},
        status=200,
    )
    assert client.get_share("trip-pool")["value"] == 0
    assert client.update_share("trip-pool", maxi="100")["maxi"] == "100"


@responses.activate
def test_error_response_raises(client):
    """A non-2xx response raises requests.HTTPError via raise_for_status()."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/api/users/me/",
        json={"detail": "Authentication credentials were not provided."},
        status=401,
    )
    with pytest.raises(requests.HTTPError):
        client.get_me()
