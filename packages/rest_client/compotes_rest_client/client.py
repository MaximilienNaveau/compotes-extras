"""Thin REST client for the compotes API."""

import requests


class CompotesClient:
    """Minimal wrapper around the compotes REST API.

    Every method maps directly to one row of the endpoint table in
    compotes' docs/03-rest-api.md - no pagination handling (none is
    configured server-side) and no retries; a non-2xx response simply
    raises `requests.HTTPError` via `raise_for_status()`.
    """

    def __init__(self, base_url, token=None, session=None):
        """Store the API base URL, and authenticate with `token` if given."""
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.token = None
        if token:
            self._set_token(token)

    def _set_token(self, token):
        self.token = token
        self.session.headers["Authorization"] = f"Token {token}"

    def _request(self, method, path, **kwargs):
        response = self.session.request(method, f"{self.base_url}/api/{path}", **kwargs)
        response.raise_for_status()
        return None if response.status_code == 204 else response.json()

    # -- Auth --------------------------------------------------------

    def login(self, username, password):
        """Exchange username+password for an auth token, and store it."""
        data = self._request(
            "post",
            "token/",
            data={"username": username, "password": password},
        )
        self._set_token(data["token"])
        return data

    def logout(self):
        """Revoke the current token."""
        self._request("post", "logout/")
        self.session.headers.pop("Authorization", None)
        self.token = None

    # -- Users ---------------------------------------------------------

    def list_users(self):
        """List users, e.g. to pick a creditor/debitor/participant."""
        return self._request("get", "users/")

    def get_me(self):
        """Return the requesting user's own record."""
        return self._request("get", "users/me/")

    # -- Events ----------------------------------------------------------

    def list_events(self):
        """List events the requesting user organises or is part of."""
        return self._request("get", "events/")

    def create_event(self, **fields):
        """Create an Event (e.g. name=, description=)."""
        return self._request("post", "events/", data=fields)

    def get_event(self, slug):
        """Retrieve one Event by slug."""
        return self._request("get", f"events/{slug}/")

    def update_event(self, slug, **fields):
        """Update an Event's given fields, e.g. name=/description=/closed_at=."""
        return self._request("patch", f"events/{slug}/", data=fields)

    def delete_event(self, slug):
        """Delete an Event."""
        return self._request("delete", f"events/{slug}/")

    def get_event_balances(self, slug):
        """Get each participant's net balance within this Event."""
        return self._request("get", f"events/{slug}/balances/")

    def close_event(self, slug, confirm=False):
        """Close the Event, folding leftover balances into the global one."""
        return self._request(
            "post",
            f"events/{slug}/close/",
            data={"confirm": confirm},
        )

    def reopen_event(self, slug):
        """Reopen a closed Event, isolating its Debts again."""
        return self._request("post", f"events/{slug}/reopen/")

    # -- Debts -----------------------------------------------------------

    def list_debts(self, **filters):
        """List debts, optionally filtered (e.g. user=, debt=)."""
        return self._request("get", "debts/", params=filters)

    def create_debt(self, **fields):
        """Create a Debt (e.g. name=, date=, creditor=, value=, event=)."""
        return self._request("post", "debts/", data=fields)

    def get_debt(self, debt_id):
        """Retrieve one Debt by id."""
        return self._request("get", f"debts/{debt_id}/")

    def update_debt(self, debt_id, **fields):
        """Update a Debt's given fields, e.g. name=/value=/description=."""
        return self._request("patch", f"debts/{debt_id}/", data=fields)

    def delete_debt(self, debt_id):
        """Delete a Debt."""
        return self._request("delete", f"debts/{debt_id}/")

    # -- Parts -------------------------------------------------------------

    def list_parts(self):
        """List parts."""
        return self._request("get", "parts/")

    def create_part(self, **fields):
        """Create a Part (e.g. debt=, debitor=, part=)."""
        return self._request("post", "parts/", data=fields)

    def get_part(self, part_id):
        """Retrieve one Part by id."""
        return self._request("get", f"parts/{part_id}/")

    def update_part(self, part_id, **fields):
        """Update a Part's given fields, e.g. part=/description=."""
        return self._request("patch", f"parts/{part_id}/", data=fields)

    def delete_part(self, part_id):
        """Delete a Part."""
        return self._request("delete", f"parts/{part_id}/")

    # -- Pools -------------------------------------------------------------

    def list_pools(self):
        """List pools the requesting user organises or shares in."""
        return self._request("get", "pools/")

    def create_pool(self, **fields):
        """Create a Pool (e.g. name=, description=, value=)."""
        return self._request("post", "pools/", data=fields)

    def get_pool(self, slug):
        """Retrieve one Pool by slug."""
        return self._request("get", f"pools/{slug}/")

    def update_pool(self, slug, **fields):
        """Update a Pool's given fields, e.g. name=/description=/value=."""
        return self._request("patch", f"pools/{slug}/", data=fields)

    def delete_pool(self, slug):
        """Delete a Pool."""
        return self._request("delete", f"pools/{slug}/")

    def get_share(self, slug):
        """Get the requesting user's Share for this Pool."""
        return self._request("get", f"pools/{slug}/share/")

    def update_share(self, slug, **fields):
        """Update the requesting user's Share for this Pool (e.g. maxi=)."""
        return self._request("put", f"pools/{slug}/share/", data=fields)
