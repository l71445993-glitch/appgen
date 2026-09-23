from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0010_githubrun_smart_multi_relay"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteEmailConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("host", models.CharField(blank=True, default="smtp.qq.com", max_length=255, verbose_name="SMTP 服务器")),
                ("port", models.PositiveIntegerField(default=465, verbose_name="端口")),
                ("username", models.CharField(blank=True, default="", max_length=255, verbose_name="发信账号")),
                ("password", models.CharField(blank=True, default="", max_length=255, verbose_name="授权码/密码")),
                ("use_ssl", models.BooleanField(default=True, verbose_name="使用 SSL")),
                ("use_tls", models.BooleanField(default=False, verbose_name="使用 TLS")),
                ("from_email", models.EmailField(blank=True, default="", max_length=254, verbose_name="发件人地址")),
                ("enabled", models.BooleanField(default=True, verbose_name="启用邮件发送")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "站点邮件配置",
                "verbose_name_plural": "站点邮件配置",
            },
        ),
    ]
