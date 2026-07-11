"""Serializers for the compotes API."""

from rest_framework import serializers

from compotes.models import Debt, Event, Part, Pool, Share, User


class UserSerializer(serializers.ModelSerializer):
    """Expose the public fields of a User."""

    class Meta:
        """Meta."""

        model = User
        fields = ["id", "username", "slug", "first_name", "last_name", "balance"]
        read_only_fields = ["slug", "balance"]


class EventSerializer(serializers.ModelSerializer):
    """Serializer for Event."""

    class Meta:
        """Meta."""

        model = Event
        fields = [
            "id",
            "name",
            "slug",
            "organiser",
            "description",
            "closed_at",
            "created",
            "updated",
        ]
        read_only_fields = ["slug", "organiser", "closed_at", "created", "updated"]


class DebtSerializer(serializers.ModelSerializer):
    """Serializer for Debt."""

    class Meta:
        """Meta."""

        model = Debt
        fields = [
            "id",
            "name",
            "date",
            "creditor",
            "event",
            "value",
            "part_value",
            "description",
            "created",
            "updated",
        ]
        read_only_fields = ["part_value", "created", "updated"]


class PartSerializer(serializers.ModelSerializer):
    """Serializer for Part."""

    class Meta:
        """Meta."""

        model = Part
        fields = ["id", "debt", "debitor", "part", "value", "description"]
        read_only_fields = ["value"]


class PoolSerializer(serializers.ModelSerializer):
    """Serializer for Pool."""

    class Meta:
        """Meta."""

        model = Pool
        fields = [
            "id",
            "name",
            "slug",
            "organiser",
            "description",
            "value",
            "ratio",
            "created",
            "updated",
        ]
        read_only_fields = ["slug", "organiser", "ratio", "created", "updated"]


class ShareSerializer(serializers.ModelSerializer):
    """Serializer for Share."""

    class Meta:
        """Meta."""

        model = Share
        fields = ["id", "pool", "participant", "maxi", "value"]
        read_only_fields = ["pool", "participant", "value"]
