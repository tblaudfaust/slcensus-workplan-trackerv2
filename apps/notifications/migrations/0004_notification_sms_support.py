from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_alter_notificationlog_rule_type_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='notificationlog',
            old_name='recipient_email',
            new_name='recipient',
        ),
        migrations.AlterField(
            model_name='notificationlog',
            name='recipient',
            field=models.CharField(max_length=254),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='channel',
            field=models.CharField(choices=[('EMAIL', 'Email'), ('SMS', 'SMS')], default='EMAIL', max_length=10),
        ),
    ]
