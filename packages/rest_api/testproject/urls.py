"""Root URLconf for compotes_rest_api's standalone test project."""

from django.urls import include, path

urlpatterns = [path("api/", include("compotes_rest_api.urls"))]
