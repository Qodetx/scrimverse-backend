from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0004_rename_screenshot_to_evidence"),
        ("tournaments", "0034_reg_tournament_status_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="broadcastemail",
            name="selected_groups",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Narrow to specific rounds/groups (e.g. 'Round 1 – Group A'). "
                    "Leave empty to include all groups."
                ),
                related_name="broadcast_emails",
                to="tournaments.group",
            ),
        ),
        migrations.AddField(
            model_name="broadcastemail",
            name="registration_status_filter",
            field=models.CharField(
                choices=[
                    ("confirmed", "Confirmed Only"),
                    ("pending", "Pending Only"),
                    ("rejected", "Rejected Only"),
                    ("all", "All Statuses"),
                ],
                default="confirmed",
                help_text="Filter registrations by status. Default: Confirmed only.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="broadcastemail",
            name="ign_filter",
            field=models.CharField(
                choices=[
                    ("all", "All Teams"),
                    ("submitted", "IGN Submitted"),
                    ("not_submitted", "IGN Not Submitted Yet"),
                ],
                default="all",
                help_text="Filter by whether the team has submitted their IGNs.",
                max_length=20,
            ),
        ),
    ]
