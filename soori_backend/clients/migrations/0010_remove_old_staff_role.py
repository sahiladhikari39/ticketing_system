from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Drops the old hardcoded staff_role text column. Split into its own
    migration deliberately -- it must run AFTER 0009 has copied every
    value out into the new StaffRole rows, otherwise the data is gone
    before anything can read it.
    """

    dependencies = [
        ("clients", "0009_populate_staff_roles"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="supportstaffprofile",
            name="staff_role",
        ),
    ]
