from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0009_registrationemailcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="githubrun",
            name="smart_multi_relay",
            field=models.BooleanField(default=False),
        ),
    ]
