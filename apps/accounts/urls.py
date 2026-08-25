from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginAPIView,
    RegisterAPIView,
    UserProfileAPIView,
)

urlpatterns = [
    path("/login", LoginAPIView.as_view(), name="user_login"),
    path("/login/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("/register", RegisterAPIView.as_view(), name="user_register"),
    path("/profile", UserProfileAPIView.as_view(), name="user_profile"),
]
