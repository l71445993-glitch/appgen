# Split combined object-storage config into independent COS / OSS singletons

from django.db import migrations, models


def forwards_split_storage(apps, schema_editor):
    Old = apps.get_model("rdgenerator", "SiteObjectStorageConfig")
    Cos = apps.get_model("rdgenerator", "SiteTencentCosConfig")
    Oss = apps.get_model("rdgenerator", "SiteAliyunOssConfig")
    old = Old.objects.filter(pk=1).first()
    cos, _ = Cos.objects.get_or_create(pk=1)
    oss, _ = Oss.objects.get_or_create(pk=1)
    if not old:
        return

    cos.key_prefix = old.key_prefix or "rdgen"
    cos.secret_id = old.cos_secret_id or ""
    cos.secret_key = old.cos_secret_key or ""
    cos.region = old.cos_region or "ap-guangzhou"
    cos.bucket = old.cos_bucket or ""
    if old.enabled and old.provider == "cos":
        cos.enabled = True
    cos.save()

    oss.key_prefix = old.key_prefix or "rdgen"
    oss.access_key_id = old.oss_access_key_id or ""
    oss.access_key_secret = old.oss_access_key_secret or ""
    oss.endpoint = old.oss_endpoint or "https://oss-cn-hangzhou.aliyuncs.com"
    oss.bucket = old.oss_bucket or ""
    if old.enabled and old.provider == "oss":
        oss.enabled = True
    oss.save()


def backwards_merge_storage(apps, schema_editor):
    Old = apps.get_model("rdgenerator", "SiteObjectStorageConfig")
    Cos = apps.get_model("rdgenerator", "SiteTencentCosConfig")
    Oss = apps.get_model("rdgenerator", "SiteAliyunOssConfig")
    old, _ = Old.objects.get_or_create(pk=1)
    cos = Cos.objects.filter(pk=1).first()
    oss = Oss.objects.filter(pk=1).first()
    if cos:
        old.key_prefix = cos.key_prefix or old.key_prefix
        old.cos_secret_id = cos.secret_id or ""
        old.cos_secret_key = cos.secret_key or ""
        old.cos_region = cos.region or "ap-guangzhou"
        old.cos_bucket = cos.bucket or ""
        if cos.enabled:
            old.enabled = True
            old.provider = "cos"
    if oss:
        old.key_prefix = oss.key_prefix or old.key_prefix
        old.oss_access_key_id = oss.access_key_id or ""
        old.oss_access_key_secret = oss.access_key_secret or ""
        old.oss_endpoint = oss.endpoint or "https://oss-cn-hangzhou.aliyuncs.com"
        old.oss_bucket = oss.bucket or ""
        if oss.enabled and not (cos and cos.enabled):
            old.enabled = True
            old.provider = "oss"
    old.save()


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0016_siteobjectstorageconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteTencentCosConfig",
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
                    models.BooleanField(default=False, verbose_name="启用腾讯云 COS"),
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
                    "secret_id",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="SecretId"
                    ),
                ),
                (
                    "secret_key",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="SecretKey"
                    ),
                ),
                (
                    "region",
                    models.CharField(
                        blank=True,
                        default="ap-guangzhou",
                        help_text="例如 ap-guangzhou / ap-shanghai",
                        max_length=64,
                        verbose_name="地域",
                    ),
                ),
                (
                    "bucket",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="完整桶名，含 APPID，例如 rdgen-artifacts-125xxxxxxx",
                        max_length=255,
                        verbose_name="桶名",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "腾讯云 COS 配置",
                "verbose_name_plural": "腾讯云 COS 配置",
            },
        ),
        migrations.CreateModel(
            name="SiteAliyunOssConfig",
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
                    models.BooleanField(default=False, verbose_name="启用阿里云 OSS"),
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
                    "access_key_id",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="AccessKeyId"
                    ),
                ),
                (
                    "access_key_secret",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="AccessKeySecret",
                    ),
                ),
                (
                    "endpoint",
                    models.CharField(
                        blank=True,
                        default="https://oss-cn-hangzhou.aliyuncs.com",
                        help_text="例如 https://oss-cn-hangzhou.aliyuncs.com",
                        max_length=255,
                        verbose_name="Endpoint",
                    ),
                ),
                (
                    "bucket",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="桶名"
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "阿里云 OSS 配置",
                "verbose_name_plural": "阿里云 OSS 配置",
            },
        ),
        migrations.RunPython(forwards_split_storage, backwards_merge_storage),
        migrations.DeleteModel(name="SiteObjectStorageConfig"),
    ]
