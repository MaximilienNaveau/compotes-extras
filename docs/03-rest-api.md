# The JSON API

The compotes web app (`compotes/views.py`, in
[MaximilienNaveau/compotes](https://github.com/MaximilienNaveau/compotes))
renders HTML. `compotes_rest_api` (this repo, [`packages/rest_api`](../packages/rest_api))
renders JSON instead, using **Django REST Framework (DRF)**, a library that
adds a JSON-specific layer on top of Django's own views/models. This doc
assumes you've read compotes'
[01-django-concepts.md](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/01-django-concepts.md).

`compotes_rest_api` depends on `compotes` (an external package from
compotes-extras' point of view) rather than the other way around — see the
root [README.md](../README.md#compotes-branches) for how the two repos fit
together, and [`compotes-rest-client`](../packages/rest_client) for a
Python client wrapping everything below.

## DRF vocabulary

- A **Serializer** is DRF's equivalent of a Django `Form`: it converts a
  model instance to JSON (`serializer.data`) and validates+converts incoming
  JSON back into Python values suitable for saving
  (`serializer.is_valid()` / `serializer.save()`).
- A **ViewSet** bundles the standard CRUD operations — list, retrieve,
  create, update, destroy — into one class, instead of five separate
  Django views. `ModelViewSet` gives you all five; `ReadOnlyModelViewSet`
  gives you just list+retrieve.
- A **Router** auto-generates URLs for a ViewSet: registering
  `PoolViewSet` under `"pools"` gives you `GET/POST /pools/` (list/create)
  and `GET/PUT/PATCH/DELETE /pools/<pk>/` (retrieve/update/destroy) for free
  — you never hand-write these five URLs.
- `@action` adds a **custom** endpoint to a ViewSet beyond those five, e.g.
  `POST /pools/<slug>/share/`.

## Every endpoint

| Method & path | View | Purpose |
|---|---|---|
| `POST /api/token/` | `LoginView` | Exchange username+password for an auth token |
| `POST /api/logout/` | `LogoutView` | Revoke the current user's token |
| `GET /api/users/` | `UserViewSet` | List users (to pick a creditor/debitor/participant) |
| `GET /api/users/me/` | `UserViewSet.me` | The requesting user's own record |
| `GET/POST /api/events/` | `EventViewSet` | List (scoped) / create an Event |
| `GET/PUT/PATCH/DELETE /api/events/<slug>/` | `EventViewSet` | Retrieve/update/delete one Event |
| `GET /api/events/<slug>/balances/` | `EventViewSet.balances` | Each participant's balance within that Event |
| `POST /api/events/<slug>/close/` | `EventViewSet.close` | Close, folding leftovers into the global balance |
| `POST /api/events/<slug>/reopen/` | `EventViewSet.reopen` | Reopen, isolating it again |
| `GET/POST /api/debts/` | `DebtViewSet` | List (filterable) / create a Debt |
| `GET/PUT/PATCH/DELETE /api/debts/<pk>/` | `DebtViewSet` | Retrieve/update/delete one Debt |
| `GET/POST /api/parts/` | `PartViewSet` | List / create a Part |
| `GET/PUT/PATCH/DELETE /api/parts/<pk>/` | `PartViewSet` | Retrieve/update/delete one Part |
| `GET/POST /api/pools/` | `PoolViewSet` | List (scoped) / create a Pool |
| `GET/PUT/PATCH/DELETE /api/pools/<slug>/` | `PoolViewSet` | Retrieve/update/delete one Pool |
| `GET/PUT /api/pools/<slug>/share/` | `PoolViewSet.share` | Get/set your own Share of that Pool |

All routes except `token`/`logout` require authentication (see
[04-auth-and-security.md](04-auth-and-security.md)). None of this is exposed
by accident — [compotes_rest_api/urls.py](../packages/rest_api/compotes_rest_api/urls.py)
registers every ViewSet explicitly with a `DefaultRouter`, and the two
non-ViewSet endpoints are listed by hand next to it.

## Serializers: what's writable, and why that's a security question

```python
class PoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pool
        fields = ["id", "name", "slug", "organiser", "description", "value", "ratio", "created", "updated"]
        read_only_fields = ["slug", "organiser", "ratio", "created", "updated"]
```
([compotes_rest_api/serializers.py](../packages/rest_api/compotes_rest_api/serializers.py))

`ModelSerializer` auto-generates one serializer field per model field listed
in `fields`, inferring the type from the model — a `ForeignKey` becomes a
`PrimaryKeyRelatedField` (accepts/returns the related row's numeric ID), a
`DecimalField` stays a decimal, etc. `read_only_fields` is not a formality:
**every field the server computes must be listed there, or a client could
set it directly.** Concretely, if `organiser` were left writable, any
authenticated user could `POST /api/pools/` with `{"organiser": <someone
else's id>}` and create a Pool that impersonates another person as its
organiser. Same logic applies to `ratio`/`part_value`/`balance`/`slug` — all
of these are values the *model's own `save()` logic* computes (compotes'
[02-data-model-and-math.md](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/02-data-model-and-math.md)),
never something a client should be trusted to set.

The actual value of `organiser`/`participant` comes from the request instead
— see the next section.

## `perform_create`/`perform_update`/`perform_destroy`

DRF's `ModelViewSet` doesn't call `serializer.save()` directly in its
`create`/`update`/`destroy` handlers — it delegates to
`perform_create`/`perform_update`/`perform_destroy`, specifically so you can
override just that one step. Two examples:

```python
def perform_create(self, serializer):
    """Set the organiser to the requesting user, then log."""
    serializer.save(organiser=self.request.user)
    self.log_action(Action.Act.CREATE, serializer.instance)
```
(`PoolViewSet`/`EventViewSet`, [compotes_rest_api/views.py](../packages/rest_api/compotes_rest_api/views.py)) — `.save()`
accepts extra keyword arguments that get merged into the instance before
saving, which is how `organiser` gets set to *the actual logged-in user*
regardless of what (if anything) the client sent — closing the impersonation
hole the read-only field alone doesn't fully close (read-only just stops the
client from sending a *different* value; this line supplies the *correct*
one).

```python
def perform_destroy(self, instance):
    """Delete a Part, then recompute the Debt & Debitor balances."""
    debt = instance.debt
    debitor = instance.debitor
    super().perform_destroy(instance)
    debitor.save()
    debt.save()
```
(`PartViewSet`) — this one exists because of a real gap: `Part.save()`
cascades to `Debt.save()` on every *save*, but deleting a row doesn't call
`.save()` at all, so nothing would otherwise trigger a balance recompute
after a Part is removed. Capturing `debt`/`debitor` *before* calling
`super().perform_destroy()` matters — the row (and Python's easy access to
its relations) is gone right after that call.

The shared logic across Debt/Part/Pool/Event — logging every create/update/
delete to the `Action` audit trail — lives in one place,
[compotes_rest_api/mixins.py](../packages/rest_api/compotes_rest_api/mixins.py)'s `ActionLoggingMixin`, and each ViewSet
mixes it in (`class DebtViewSet(ActionLoggingMixin, viewsets.ModelViewSet)`)
rather than repeating the same three methods four times.

## Custom actions

```python
@action(detail=True, methods=["get", "put"])
def share(self, request, slug=None):
    pool = self.get_object()
    share, _created = Share.objects.get_or_create(pool=pool, participant=request.user)
    ...
```
(`PoolViewSet.share`, [compotes_rest_api/views.py](../packages/rest_api/compotes_rest_api/views.py)) — `detail=True` means
this action operates on *one* Pool (so it's routed under
`/pools/<slug>/share/`, not `/pools/share/`); `methods=[...]` restricts which
HTTP verbs reach it. `get_or_create` is a Django QuerySet method that
fetches a row matching the given filters, or creates one with those same
values if none exists — used here so that visiting your own Share for a Pool
you've never pledged to yet transparently creates a zero pledge instead of
404ing.

`EventViewSet` has three: `balances` (`GET`, read-only, exists purely to let
a client show "who owes whom in this trip" — see compotes'
[02-data-model-and-math.md § Event math](https://github.com/MaximilienNaveau/compotes/blob/extras-base/docs/02-data-model-and-math.md#event-math-isolating-a-sub-ledger)
for the math it wraps), `close`, and `reopen` (both `POST`, since they
mutate state — a `GET` should never have side effects). Router-generated
names for these follow `{basename}-{method_name}`, so tests/clients reverse
them as `compotes_rest_api:event-balances`, `compotes_rest_api:event-close`,
`compotes_rest_api:event-reopen`.

## Case study: a real bug this design caught

`PoolViewSet.get_queryset` (and `EventViewSet`'s, added later, copying the
same shape) originally filtered **every** action to "pools/events the user
organises or already participates in":

```python
def get_queryset(self):
    return Pool.objects.filter(Q(organiser=user) | Q(share__participant=user)).distinct()
```

That's correct for the **list** action (don't show a user pools they have no
connection to) but it silently broke **joining a new pool by its share
link**: `PoolViewSet.share` calls `self.get_object()`, which uses this same
`get_queryset()` — so a user with no existing Share in that Pool yet (i.e.
exactly the person trying to join for the first time) got a `404` before
even reaching the "create my share" logic. This is caught almost immediately
by `test_pool_and_share_flow` failing with a 404 instead of 200 the first
time it was written. The fix, in both ViewSets, is to only apply the
restrictive filter for the `list` action and leave every other action
(`retrieve`, `update`, `share`, `close`, ...) using the full unfiltered
queryset:

```python
def get_queryset(self):
    queryset = Pool.objects.all()
    if self.action == "list":
        queryset = queryset.filter(Q(organiser=user) | Q(share__participant=user)).distinct()
    return queryset
```

The lesson generalizes: **`get_queryset()` on a ViewSet applies to every
action unless you branch on `self.action`.** A filter that's correct for a
listing page can be wrong for a detail/action endpoint reached by a
different, valid user journey (here: "I was sent a link to a pool I've never
seen before"). This is exactly the kind of thing worth testing explicitly
for any ViewSet you add — a passing `list` test tells you nothing about
whether `retrieve` or a custom `@action` on the same class got the
same treatment right.

Next: [04-auth-and-security.md](04-auth-and-security.md) covers how a client
authenticates against all of this, and what happens if someone tries to
brute-force a password.
