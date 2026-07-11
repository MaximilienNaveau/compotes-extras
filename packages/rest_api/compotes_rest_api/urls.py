"""URL Configuration for the compotes API."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import (
    DebtViewSet,
    EventViewSet,
    LoginView,
    LogoutView,
    PartViewSet,
    PoolViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("events", EventViewSet, basename="event")
router.register("debts", DebtViewSet, basename="debt")
router.register("parts", PartViewSet, basename="part")
router.register("pools", PoolViewSet, basename="pool")

app_name = "compotes_rest_api"
urlpatterns = [
    path("token/", LoginView.as_view(), name="token"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", include(router.urls)),
]
