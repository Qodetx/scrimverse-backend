from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0037_notification_type_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='hostprofile',
            name='payout_details',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Payout details (private): {"method": "bank"|"upi", "bank_name": "...", "account_number": "...", "ifsc_code": "...", "upi_id": "..."}',
            ),
        ),
    ]
