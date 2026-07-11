"""Mixins for API viewsets."""

from actions.models import Action, to_json


class ActionLoggingMixin:
    """Log Create/Update/Delete actions performed through a ViewSet."""

    def log_action(self, act, instance):
        """Record an Action entry for the current user."""
        Action.objects.create(user=self.request.user, act=act, json=to_json(instance))

    def perform_create(self, serializer):
        """Save and log a creation."""
        serializer.save()
        self.log_action(Action.Act.CREATE, serializer.instance)

    def perform_update(self, serializer):
        """Save and log an update."""
        serializer.save()
        self.log_action(Action.Act.UPDATE, serializer.instance)

    def perform_destroy(self, instance):
        """Log then delete."""
        self.log_action(Action.Act.DELETE, instance)
        instance.delete()
