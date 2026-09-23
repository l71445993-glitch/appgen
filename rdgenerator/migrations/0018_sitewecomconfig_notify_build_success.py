from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdgenerator", "0017_split_cos_oss_configs"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitewecomconfig",
            name="notify_build_success",
            field=models.BooleanField("构建成功提醒", default=False),
        ),
    ]
