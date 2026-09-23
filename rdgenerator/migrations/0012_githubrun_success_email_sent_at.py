from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0011_siteemailconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="githubrun",
            name="success_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
