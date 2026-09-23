# Generated manually for COS / OSS admin settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0015_sitewecomconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteObjectStorageConfig",
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
                    models.BooleanField(default=False, verbose_name="启用对象存储中转"),
                ),
                (
                    "provider",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "未启用"),
                            ("cos", "腾讯云 COS"),
                            ("oss", "阿里云 OSS"),
                        ],
                        default="",
                        max_length=16,
                        verbose_name="当前提供商",
                    ),
                ),
                (
                    "key_prefix",
                    models.CharField(
                        blank=True,
                        default="rdgen",
                        help_text="例如 rdgen → rdgen/{uuid}/filename.exe",
                        max_length=128,
                        verbose_name="对象前缀",
                    ),
                ),
                (
                    "cos_secret_id",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="COS SecretId"
                    ),
                ),
                (
                    "cos_secret_key",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="COS SecretKey"
                    ),
                ),
                (
                    "cos_region",
                    models.CharField(
                        blank=True,
                        default="ap-guangzhou",
                        help_text="例如 ap-guangzhou / ap-shanghai",
                        max_length=64,
                        verbose_name="COS 地域",
                    ),
                ),
                (
                    "cos_bucket",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="完整桶名，含 APPID，例如 rdgen-artifacts-125xxxxxxx",
                        max_length=255,
                        verbose_name="COS 桶名",
                    ),
                ),
                (
                    "oss_access_key_id",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="OSS AccessKeyId",
                    ),
                ),
                (
                    "oss_access_key_secret",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="OSS AccessKeySecret",
                    ),
                ),
                (
                    "oss_endpoint",
                    models.CharField(
                        blank=True,
                        default="https://oss-cn-hangzhou.aliyuncs.com",
                        help_text="例如 https://oss-cn-hangzhou.aliyuncs.com",
                        max_length=255,
                        verbose_name="OSS Endpoint",
                    ),
                ),
                (
                    "oss_bucket",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="OSS 桶名"
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "对象存储配置",
                "verbose_name_plural": "对象存储配置",
            },
        ),
    ]
