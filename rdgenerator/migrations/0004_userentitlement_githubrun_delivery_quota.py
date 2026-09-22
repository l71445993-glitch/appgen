from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_entitlements(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserEntitlement = apps.get_model("rdgenerator", "UserEntitlement")
    UserEntitlement.objects.bulk_create(
        [
            UserEntitlement(
                user_id=user.pk,
                expiration_mode="time",
                expires_at=None,
                generation_limit=None,
                generations_used=0,
                reserved_generations=0,
            )
            for user in User.objects.only("pk").iterator()
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("rdgenerator", "0003_githubrun_owner"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserEntitlement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "expiration_mode",
                    models.CharField(
                        choices=[("time", "按时间"), ("count", "按生成次数")],
                        default="time",
                        max_length=10,
                    ),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "generation_limit",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("generations_used", models.PositiveIntegerField(default=0)),
                ("reserved_generations", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entitlement",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "用户生成额度",
                "verbose_name_plural": "用户生成额度",
            },
        ),
        migrations.AddField(
            model_name="githubrun",
            name="download_access",
            field=models.CharField(default="login", max_length=10),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="download_ttl_hours",
            field=models.PositiveSmallIntegerField(default=168),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="download_token_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="download_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="artifact_uploaded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="artifact_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="artifact_file_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="quota_reserved",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="githubrun",
            name="quota_counted",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(create_default_entitlements, migrations.RunPython.noop),
    ]
