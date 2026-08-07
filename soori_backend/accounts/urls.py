from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    ChangePasswordView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    SooriTokenObtainPairView,
)

urlpatterns = [
    path("token/", SooriTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
]
