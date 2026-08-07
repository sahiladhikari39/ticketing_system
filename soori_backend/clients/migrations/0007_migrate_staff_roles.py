from django.db import migrations

# Old scale was seniority-based (agent -> senior_agent -> supervisor).
# The new one is function-based: you either coordinate, or you attend
# sites. Mapping keeps the meaning rather than the label:
#
#   agent / senior_agent -> field_engineer
#       These were the people tickets got ASSIGNED to, i.e. the ones
#       doing the actual work. That's the Field Engineer's job now.
#
#   supervisor -> service_department
#       Supervisors were the only staff tier allowed to reassign
#       tickets. Coordinating who goes where is exactly what the
#       Service Department does.
FORWARD_MAP = {
    "agent": "field_engineer",
    "senior_agent": "field_engineer",
    "supervisor": "service_department",
}

# Reverse is lossy -- two old values collapse into one new one, so
# going back can only pick a sensible representative.
BACKWARD_MAP = {
    "field_engineer": "agent",
    "service_department": "supervisor",
}


def forwards(apps, schema_editor):
    SupportStaffProfile = apps.get_model("clients", "SupportStaffProfile")
    for old, new in FORWARD_MAP.items():
        SupportStaffProfile.objects.filter(staff_role=old).update(staff_role=new)


def backwards(apps, schema_editor):
    SupportStaffProfile = apps.get_model("clients", "SupportStaffProfile")
    for new, old in BACKWARD_MAP.items():
        SupportStaffProfile.objects.filter(staff_role=new).update(staff_role=old)


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0006_subclientprofile_service_area_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
