from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import User


class UserCreationFormWithRole(UserCreationForm):
    """
    Django's stock "Add user" page only has username + password --
    role and client aren't on it, but User.clean() requires them to
    already be consistent on that very first save (see the
    CheckConstraint in models.py). Without this, creating any user
    through /admin/ (other than via createsuperuser) fails immediately
    with "... users must belong to a Client." before you ever get the
    chance to set role/client on the follow-up edit page.
    """

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "role", "client")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreationFormWithRole
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "role", "client"),
        }),
    )
    list_display = ("username", "email", "role", "client", "is_active")
    list_filter = ("role", "client", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Tenant / Role", {"fields": ("role", "client")}),
    )
