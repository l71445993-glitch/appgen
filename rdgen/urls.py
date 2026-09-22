"""URL configuration for the RustDesk generator."""

from django.http import JsonResponse
from django.urls import include, path

from rdgenerator import views


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", include("rdgenerator.auth_urls")),
    path("", views.generator_view, name="generator"),
    path("generator", views.generator_view, name="generator_short"),
    path("check_for_file", views.check_for_file, name="check_for_file"),
    path("download", views.download, name="download"),
    path("updategh", views.update_github_run, name="update_github_run"),
    path("startgh", views.startgh, name="start_github"),
    path("get_png", views.get_png, name="get_png"),
    path("save_custom_client", views.save_custom_client, name="save_custom_client"),
    path(
        "finalize_custom_client",
        views.finalize_custom_client,
        name="finalize_custom_client",
    ),
    path("get_zip", views.get_zip, name="get_zip"),
    path("cleanzip", views.cleanup_secrets, name="cleanup_secrets"),
    path("healthz", healthz, name="healthz"),
]
