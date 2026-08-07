from django.db import migrations

# Permission codes, duplicated as literals on purpose. A migration has
# to keep working against the code as it was WHEN IT RAN -- importing
# StaffPermission from the live models would mean this migration
# silently changes behaviour if those constants are ever renamed.
ASSIGN_TICKETS = "tickets.assign"
RECEIVE_TICKETS = "tickets.receive"
VIEW_REPORTS = "reports.view"
MANAGE_TEAM = "team.manage"
VIEW_AUDIT_LOG = "audit.view"

# The two roles every company starts with, matching the workflow:
# the Service Department coordinates and assigns; the Field Engineer
# attends the site and does the work.
DEFAULT_ROLES = {
    "Service Department": {
        "description": "Coordinates incoming tickets and assigns Field Engineers.",
        "permissions": [ASSIGN_TICKETS, VIEW_REPORTS, "service_report.approve",
                        "service_report.view_all", "knowledge_base.view"],
    },
    "Field Engineer": {
        "description": "Attends the customer site and resolves the ticket.",
        "permissions": [RECEIVE_TICKETS, VIEW_REPORTS, "service_report.write"],
    },
}

# Old hardcoded value -> which default role that person becomes.
OLD_VALUE_TO_ROLE = {
    "service_department": "Service Department",
    "field_engineer": "Field Engineer",
    # Safety net for any row that predates even the previous rename
    # and somehow escaped migration 0007.
    "agent": "Field Engineer",
    "senior_agent": "Field Engineer",
    "supervisor": "Service Department",
}


def forwards(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    StaffRole = apps.get_model("clients", "StaffRole")
    SupportStaffProfile = apps.get_model("clients", "SupportStaffProfile")

    # Every existing company gets the default role set, so nobody ends
    # up with staff pointing at nothing.
    roles_by_client = {}
    for client in Client.objects.all():
        roles_by_client[client.id] = {}
        for name, config in DEFAULT_ROLES.items():
            role, _ = StaffRole.objects.get_or_create(
                client=client,
                name=name,
                defaults={
                    "description": config["description"],
                    "permissions": config["permissions"],
                    "is_system": True,
                },
            )
            roles_by_client[client.id][name] = role

    for profile in SupportStaffProfile.objects.select_related("user").all():
        client_id = profile.user.client_id
        if client_id is None:
            continue
        role_name = OLD_VALUE_TO_ROLE.get(profile.staff_role, "Service Department")
        role = roles_by_client.get(client_id, {}).get(role_name)
        if role is not None:
            profile.role = role
            profile.save(update_fields=["role"])


def backwards(apps, schema_editor):
    """Write the role name back into the old text column."""
    SupportStaffProfile = apps.get_model("clients", "SupportStaffProfile")
    reverse_map = {"Service Department": "service_department", "Field Engineer": "field_engineer"}
    for profile in SupportStaffProfile.objects.select_related("role").all():
        if profile.role_id:
            profile.staff_role = reverse_map.get(profile.role.name, "service_department")
            profile.save(update_fields=["staff_role"])


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0008_add_dynamic_staff_roles"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
