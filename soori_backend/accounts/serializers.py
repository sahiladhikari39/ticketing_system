from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import PasswordResetOTP, User


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Step 1: someone enters their email and we send them a 6-digit code.

    Deliberately does NOT reveal whether that email has an account.
    Saying "no account with that email" would turn this endpoint into
    a free membership-checker -- feed it a list of addresses and learn
    which ones are registered. So the response is identical either
    way, and we simply don't send anything when there's no match.
    """

    email = serializers.EmailField()

    def save(self):
        from .notifications import send_password_reset_code

        email = self.validated_data["email"]
        # is_active=False covers soft-deleted people (see
        # User.soft_delete) -- someone removed from a team shouldn't be
        # able to reset their way back in.
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            return  # Silently do nothing -- see the docstring above.

        _, code = PasswordResetOTP.generate_for(user)
        send_password_reset_code(user, code)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Step 2: the code from the email, plus the email it was sent to and
    the new password.

    Email is required alongside the code so a code can only ever be
    checked against the account it was issued for -- otherwise a
    6-digit code would effectively be valid against EVERY account at
    once, which massively widens what a brute-force attempt could hit.
    """

    email = serializers.EmailField()
    code = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        generic_error = "That code isn't valid. Please check it or request a new one."

        user = User.objects.filter(email__iexact=attrs["email"], is_active=True).first()
        if user is None:
            # Same wording as a wrong code, so this doesn't become an
            # account-existence check either.
            raise serializers.ValidationError({"code": generic_error})

        otp = PasswordResetOTP.objects.filter(user=user, used_at__isnull=True).first()
        if otp is None:
            raise serializers.ValidationError({"code": generic_error})

        # Password strength is checked BEFORE the code, deliberately.
        # verify() consumes the code on success -- so checking the
        # password afterwards meant a too-short password burned the
        # code, forcing the person to request a new one just because
        # they picked a weak password. (That happened in testing.)
        # Ordering costs nothing security-wise: an attacker probing
        # codes would simply submit a strong password anyway, so the
        # reverse order never actually protected the code.
        validate_password(attrs["new_password"], user=user)

        ok, error = otp.verify(attrs["code"].strip())
        if not ok:
            raise serializers.ValidationError({"code": error})

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class UserSerializer(serializers.ModelSerializer):
    """
    Serializes the currently authenticated user. Used by /api/me/ so
    the frontend can ask "who am I, and what can I do" right after
    login (or on every page load) without decoding the JWT itself.
    """

    # The frontend needs these to hide navigation the person genuinely
    # can't use. Showing a Field Engineer a "Knowledge Base" link that
    # loads an empty page technically enforces the rule but reads as a
    # bug -- and the company's requirement was that the video library
    # is never available to them at all, not merely always empty.
    #
    # This is convenience only. Every one of these permissions is
    # enforced independently server-side; a tampered client payload
    # buys nothing.
    staff_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "client", "staff_permissions",
        ]
        read_only_fields = fields

    def get_staff_permissions(self, obj):
        from clients.models import StaffPermission

        # A Client Admin implicitly holds everything inside their own
        # company (see User.has_staff_perm), so report the full set
        # rather than an empty list.
        if obj.role == "client_admin":
            return StaffPermission.ALL
        profile = getattr(obj, "staff_profile", None)
        if profile is None or profile.role_id is None:
            return []
        return list(profile.role.permissions or [])


class ChangePasswordSerializer(serializers.Serializer):
    """
    Used by POST /api/change-password/. Requires the CURRENT password,
    not just a new one -- without that check, anyone who steals a
    logged-in session (a valid access token) could lock the real owner
    out permanently by changing their password to something only the
    attacker knows. Confirming the current password first means an
    attacker still needs to already know the password to change it,
    which somewhat limits what a stolen-token-only attack can do here.
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        # Django's validate_password runs every validator listed in
        # AUTH_PASSWORD_VALIDATORS (settings.py) -- minimum length,
        # not-too-common, not-all-numeric, not-too-similar to the
        # user's own username/email.
        user = self.context["request"].user
        validate_password(value, user=user)
        return value

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class SooriTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Adds `role` and `client_id` directly into the JWT payload, not just
    into the login response body.

    Why put it in the token itself, instead of only returning it once
    at login?
    - The frontend can decode the JWT locally (it's just base64 --  no
      network call, no library beyond a JWT decoder) to know the
      user's role/tenant immediately on page load or after a refresh,
      without waiting on a round trip to /api/me/.
    - Every authenticated request already carries the token in its
      Authorization header, so anything that wants "who is this and
      which tenant are they in" (logging, middleware, rate limiting
      per-tenant, etc.) can read it straight off the validated token
      without an extra DB hit.

    Trade-off you accept: this data is only as fresh as the token.
    If an admin changes someone's role mid-session, that user won't see
    it reflected until their access token is refreshed. Given
    ACCESS_TOKEN_LIFETIME is 30 minutes here, that's a bounded staleness
    window, not a permanent one -- acceptable for this use case, but
    worth knowing if you ever need instant role-change propagation
    (you'd need to blacklist their existing tokens on role change).
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["client_id"] = str(user.client_id) if user.client_id else None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Also return full user info in the login response body itself,
        # so the frontend doesn't need a *second* call just to render
        # "logged in as ___" right after login.
        data["user"] = UserSerializer(self.user).data
        return data
