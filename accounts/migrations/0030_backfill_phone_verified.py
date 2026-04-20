from django.db import migrations


def backfill_phone_verified(apps, schema_editor):
    """Set is_phone_verified=True for all users who already have a phone number.
    These users verified their phone during registration (OTP flow) before this
    field was tracked explicitly."""
    User = apps.get_model('accounts', 'User')
    User.objects.filter(
        phone_number__isnull=False
    ).exclude(
        phone_number=''
    ).update(is_phone_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0029_add_phone_verified_field'),
    ]

    operations = [
        migrations.RunPython(backfill_phone_verified, migrations.RunPython.noop),
    ]
