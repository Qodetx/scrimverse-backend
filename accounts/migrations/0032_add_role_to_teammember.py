from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0031_data_export_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='teammember',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('IGL', 'IGL'),
                    ('Assaulter', 'Assaulter'),
                    ('Support', 'Support'),
                    ('Scout', 'Scout'),
                    ('Sniper', 'Sniper'),
                    ('Rusher', 'Rusher'),
                    ('Duelist', 'Duelist'),
                    ('Controller', 'Controller'),
                    ('Sentinel', 'Sentinel'),
                    ('Initiator', 'Initiator'),
                    ('Flex', 'Flex'),
                    ('Member', 'Member'),
                ],
                default='Member',
                max_length=20,
            ),
        ),
    ]
