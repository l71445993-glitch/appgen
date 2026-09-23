from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0012_githubrun_success_email_sent_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="githubrun",
            name="config_snapshot",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
