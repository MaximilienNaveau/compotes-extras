"""Viewsets for the compotes API."""

from django.db.models import Q

from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from actions.models import Action
from compotes.filters import DebtFilter
from compotes.models import Debt, Event, Part, Pool, Share, User

from .mixins import ActionLoggingMixin
from .serializers import (
    DebtSerializer,
    EventSerializer,
    PartSerializer,
    PoolSerializer,
    ShareSerializer,
    UserSerializer,
)


class LoginRateThrottle(AnonRateThrottle):
    """Dedicated, tighter throttle scope for login attempts.

    DRF's ObtainAuthToken sets throttle_classes = () by default, opting out
    of the global DEFAULT_THROTTLE_CLASSES entirely, so login needs its own.
    """

    scope = "login"


class LoginView(ObtainAuthToken):
    """Obtain an auth token, throttled against password guessing."""

    throttle_classes = [LoginRateThrottle]


class LogoutView(APIView):
    """Revoke the requesting user's API token.

    There is a single token per user (not one per device), so this also
    kicks out any other device still using it, e.g. after losing a phone.
    Reachable via the current token, or via a logged-in browser session.
    """

    def post(self, request):
        """Delete the token, forcing every API client to log in again."""
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """List & retrieve Users, e.g. to pick a creditor/debitor/participant."""

    queryset = User.objects.all()
    serializer_class = UserSerializer

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Return the requesting user."""
        return Response(self.get_serializer(request.user).data)


class EventViewSet(ActionLoggingMixin, viewsets.ModelViewSet):
    """CRUD for Events, plus close/reopen/balances actions."""

    serializer_class = EventSerializer
    lookup_field = "slug"

    def get_queryset(self):
        """Restrict the list to events the user organises or is part of.

        Detail actions (retrieve/update/close/...) stay unfiltered so a user
        can join an event they only know the slug of, mirroring PoolViewSet.
        """
        queryset = Event.objects.all()
        if self.action == "list":
            user = self.request.user
            queryset = queryset.filter(
                Q(organiser=user)
                | Q(debt__creditor=user)
                | Q(debt__part__debitor=user),
            ).distinct()
        return queryset

    def perform_create(self, serializer):
        """Set the organiser to the requesting user, then log."""
        serializer.save(organiser=self.request.user)
        self.log_action(Action.Act.CREATE, serializer.instance)

    def _balances(self, event):
        """Compute each participant's net balance within this Event."""
        return [
            {
                "user": UserSerializer(user).data,
                "balance": user.get_event_balance(event),
            }
            for user in event.participants()
        ]

    @action(detail=True, methods=["get"])
    def balances(self, request, slug=None):
        """Get each participant's net balance within this Event."""
        return Response(self._balances(self.get_object()))

    @action(detail=True, methods=["post"])
    def close(self, request, slug=None):
        """Close the Event, requiring confirmation if balances aren't settled."""
        event = self.get_object()
        balances = self._balances(event)
        unsettled = [b for b in balances if b["balance"] != 0]
        confirmed = str(request.data.get("confirm", "")).lower() in ("1", "true")
        if unsettled and not confirmed:
            return Response(
                {
                    "detail": (
                        "Some balances are not settled yet. Resend with "
                        "confirm=true to close anyway and fold them into "
                        "the global balance."
                    ),
                    "balances": balances,
                },
                status=status.HTTP_409_CONFLICT,
            )
        event.close()
        self.log_action(Action.Act.UPDATE, event)
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, slug=None):
        """Reopen a closed Event, isolating its Debts again."""
        event = self.get_object()
        event.reopen()
        self.log_action(Action.Act.UPDATE, event)
        return Response(self.get_serializer(event).data)


class DebtViewSet(ActionLoggingMixin, viewsets.ModelViewSet):
    """CRUD for Debts."""

    queryset = Debt.objects.all()
    serializer_class = DebtSerializer
    filterset_class = DebtFilter


class PartViewSet(ActionLoggingMixin, viewsets.ModelViewSet):
    """CRUD for Parts."""

    queryset = Part.objects.all()
    serializer_class = PartSerializer

    def perform_destroy(self, instance):
        """Delete a Part, then recompute the Debt & Debitor balances."""
        debt = instance.debt
        debitor = instance.debitor
        super().perform_destroy(instance)
        debitor.save()
        debt.save()


class PoolViewSet(ActionLoggingMixin, viewsets.ModelViewSet):
    """CRUD for Pools, plus a `share` action for one's own Share."""

    serializer_class = PoolSerializer
    lookup_field = "slug"

    def get_queryset(self):
        """Restrict the list to pools the user organises or shares in.

        Detail actions (retrieve/update/share/...) stay unfiltered so a user
        can join a pool they only know the slug of, mirroring PoolDetailView.
        """
        queryset = Pool.objects.all()
        if self.action == "list":
            user = self.request.user
            queryset = queryset.filter(
                Q(organiser=user) | Q(share__participant=user),
            ).distinct()
        return queryset

    def perform_create(self, serializer):
        """Set the organiser to the requesting user, then log."""
        serializer.save(organiser=self.request.user)
        self.log_action(Action.Act.CREATE, serializer.instance)

    @action(detail=True, methods=["get", "put"])
    def share(self, request, slug=None):
        """Get or update the requesting user's Share for this Pool."""
        pool = self.get_object()
        share, _created = Share.objects.get_or_create(
            pool=pool,
            participant=request.user,
        )
        if request.method == "PUT":
            serializer = ShareSerializer(share, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            self.log_action(Action.Act.UPDATE, share)
            return Response(serializer.data)
        return Response(ShareSerializer(share).data)
