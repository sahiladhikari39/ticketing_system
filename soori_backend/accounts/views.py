from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SooriTokenObtainPairSerializer,
    UserSerializer,
)


class SooriTokenObtainPairView(TokenObtainPairView):
    """POST {username, password} -> {access, refresh, user}."""

    serializer_class = SooriTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView):
    """
    GET /api/me/ -- "who am I". The JWT stays the source of truth for
    *access* (every other endpoint validates it independently on every
    request); this endpoint is a convenience for the frontend to fetch
    full profile fields the token payload doesn't carry (email, full
    name, etc.) without you having to keep decoding the JWT client-side
    every time you need something beyond role/client_id.
    """

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """
    POST /api/change-password/ -- {current_password, new_password}.
    Any authenticated user, any role -- this is entirely self-service,
    there's no "change someone else's password" version of this.

    Known limitation, worth naming rather than hiding: this does NOT
    invalidate the person's existing JWT access/refresh tokens. Without
    token blacklisting (not built yet -- flagged back when JWT auth was
    first added), an access token issued before the password change
    stays valid until it naturally expires (30 minutes). The password
    itself is genuinely changed the instant this succeeds; it's only
    an *already-issued* token that keeps working a little longer.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """
    POST /api/password-reset/ -- {email}

    AllowAny on purpose: someone who's forgotten their password is by
    definition unable to authenticate first.

    Always returns the same success response, whether or not that
    email has an account. See PasswordResetRequestSerializer for why
    (short version: telling the caller "no such account" would let
    anyone test which email addresses are registered).
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "If an account exists for that email, a reset link has been sent."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/password-reset/confirm/ -- {uid, token, new_password}

    Also AllowAny -- the uid+token pair from the emailed link IS the
    proof of identity here, standing in for being logged in.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password reset successfully. You can now log in with your new password."},
            status=status.HTTP_200_OK,
        )
