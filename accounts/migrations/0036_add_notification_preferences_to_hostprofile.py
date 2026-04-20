from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0035_add_social_links_to_hostprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='hostprofile',
            name='notification_preferences',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Host notification preferences: {newRegistrations, matchAlerts, paymentAlerts, systemUpdates}',
            ),
        ),
    ]
