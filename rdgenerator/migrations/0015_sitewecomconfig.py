# Generated manually for WeCom admin alerts

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0014_admin_ops_suite"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteWecomConfig",
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
                    "enabled",
                    models.BooleanField(default=False, verbose_name="启用企业微信通知"),
                ),
                (
                    "webhook_url",
                    models.URLField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="机器人 Webhook 地址",
                    ),
                ),
                (
                    "notify_remote_login",
                    models.BooleanField(default=True, verbose_name="异地登录提醒"),
                ),
                (
                    "notify_admin_login",
                    models.BooleanField(default=False, verbose_name="超管登录成功提醒"),
                ),
                (
                    "notify_build_failure",
                    models.BooleanField(default=True, verbose_name="构建失败提醒"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "企业微信通知配置",
                "verbose_name_plural": "企业微信通知配置",
            },
        ),
    ]
