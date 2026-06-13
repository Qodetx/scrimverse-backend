from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communications', '0003_issuereport_screenshot'),
    ]

    operations = [
        migrations.RenameField(
            model_name='issuereport',
            old_name='screenshot',
            new_name='evidence',
        ),
        migrations.AlterField(
            model_name='issuereport',
            name='evidence',
            field=models.FileField(blank=True, null=True, upload_to='reports/'),
        ),
    ]
