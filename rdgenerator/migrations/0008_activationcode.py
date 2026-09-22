from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("rdgenerator", "0007_githubrun_artifact_contract_generatedartifact"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivationCode",
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
                    "code_hash",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                ("code_hint", models.CharField(editable=False, max_length=4)),
                (
                    "plan",
                    models.CharField(
                        choices=[
                            ("single", "次卡（1 次生成）"),
                            ("3day", "3 日卡"),
                            ("week", "周卡（7 天）"),
                            ("month", "月卡（30 天）"),
                            ("lifetime", "终身卡"),
                        ],
                        db_index=True,
                        max_length=12,
                    ),
                ),
                ("batch_label", models.CharField(blank=True, default="", max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("redeemed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activation_codes_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "redeemed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activation_codes_redeemed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activation_codes_revoked",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "会员激活码",
                "verbose_name_plural": "会员激活码",
                "ordering": ("-created_at", "-pk"),
            },
        ),
    ]
