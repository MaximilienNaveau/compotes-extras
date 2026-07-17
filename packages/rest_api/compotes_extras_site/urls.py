"""Full-stack urls: compotes' own urlpatterns, plus /api/."""

from django.urls import include, path

from compotes.urls import urlpatterns as compotes_urlpatterns

urlpatterns = [
    *compotes_urlpatterns,
    path("api/", include("compotes_rest_api.urls")),
]
