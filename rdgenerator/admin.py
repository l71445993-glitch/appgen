from django.contrib import admin

from .models import ActivationCode, GithubRun


@admin.register(GithubRun)
class GithubRunAdmin(admin.ModelAdmin):
    list_display = ("uuid", "owner", "status", "github_run_id", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("uuid", "status", "owner__username")
    readonly_fields = (
        "id",
        "uuid",
        "owner",
        "status",
        "github_run_id",
        "created_at",
        "callback_token_hash",
    )


@admin.register(ActivationCode)
class ActivationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "masked_code",
        "plan",
        "status_label",
        "batch_label",
        "redeemed_by",
        "created_at",
    )
    list_filter = ("plan", "created_at", "redeemed_at", "revoked_at")
    search_fields = ("code_hint", "batch_label", "redeemed_by__username")
    readonly_fields = (
        "code_hash",
        "code_hint",
        "plan",
        "batch_label",
        "created_by",
        "created_at",
        "redeemed_by",
        "redeemed_at",
        "revoked_by",
        "revoked_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
