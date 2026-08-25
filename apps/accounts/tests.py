from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)

User = get_user_model()


class AccountsModelTests(TestCase):
    def test_user_str_returns_username(self):
        user = User.objects.create_user(
            username="struser",
            email="struser@example.com",
            password="password",
        )
        self.assertEqual(str(user), "struser")

    def test_user_ordering_is_by_id(self):
        user_b = User.objects.create_user(
            username="user_b",
            email="b@example.com",
            password="password",
        )
        user_a = User.objects.create_user(
            username="user_a",
            email="a@example.com",
            password="password",
        )
        users = list(User.objects.all())
        self.assertEqual(users[0].pk, min(user_a.pk, user_b.pk))


class RegisterSerializerTests(TestCase):
    def setUp(self):
        self.existing = User.objects.create_user(
            username="existing",
            email="existing@example.com",
            password="password",
        )

    def test_validate_username_rejects_duplicate(self):
        serializer = RegisterSerializer(
            data={
                "username": "existing",
                "email": "new@example.com",
                "password": "SecurePass123!",
                "password_confirm": "SecurePass123!",
            },
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("username", serializer.errors)

    def test_validate_email_lowercases_and_rejects_duplicate(self):
        serializer = RegisterSerializer(
            data={
                "username": "newuser",
                "email": "Existing@Example.com",
                "password": "SecurePass123!",
                "password_confirm": "SecurePass123!",
            },
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

    def test_validate_password_mismatch(self):
        serializer = RegisterSerializer(
            data={
                "username": "newuser",
                "email": "new@example.com",
                "password": "SecurePass123!",
                "password_confirm": "Different123!",
            },
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("password_confirm", serializer.errors)

    def test_valid_serializer_passes_all_checks(self):
        serializer = RegisterSerializer(
            data={
                "username": "newuser",
                "email": "new@example.com",
                "first_name": "",
                "last_name": "",
                "password": "SecurePass123!",
                "password_confirm": "SecurePass123!",
            },
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_weak_password_fails_password_validation(self):
        serializer = RegisterSerializer(
            data={
                "username": "newuser",
                "email": "new@example.com",
                "password": "12345678",
                "password_confirm": "12345678",
            },
        )
        self.assertFalse(serializer.is_valid())


class UserProfileUpdateSerializerTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username="alpha",
            email="alpha@example.com",
            password="password",
        )
        self.user_b = User.objects.create_user(
            username="beta",
            email="beta@example.com",
            password="password",
        )

    def test_validate_username_rejects_other_users_username(self):
        serializer = UserProfileUpdateSerializer(
            instance=self.user_a,
            data={"username": "beta", "email": "alpha@example.com"},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("username", serializer.errors)

    def test_validate_username_allows_same_username(self):
        serializer = UserProfileUpdateSerializer(
            instance=self.user_a,
            data={"username": "alpha", "email": "alpha@example.com"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_validate_email_rejects_other_users_email(self):
        serializer = UserProfileUpdateSerializer(
            instance=self.user_a,
            data={"username": "alpha", "email": "Beta@Example.com"},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)


class LoginSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="loginme",
            email="loginme@example.com",
            password="SecurePass123!",
        )

    def test_get_token_includes_username_and_email(self):
        token = LoginSerializer.get_token(self.user)
        self.assertEqual(token["username"], "loginme")
        self.assertEqual(token["email"], "loginme@example.com")


class AccountsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse("user_register")
        self.login_url = reverse("user_login")
        self.profile_url = reverse("user_profile")

    def test_user_registration_success(self):
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["username"], "testuser")
        self.assertEqual(User.objects.count(), 1)

    def test_user_registration_password_mismatch(self):
        data = {
            "username": "testuser2",
            "email": "test2@example.com",
            "password": "SecurePass123!",
            "password_confirm": "WrongPass456!",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_user_registration_duplicate_email(self):
        User.objects.create_user(
            username="first",
            email="duplicate@example.com",
            password="password",
        )
        data = {
            "username": "second",
            "email": "Duplicate@Example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_user_login_success(self):
        _user = User.objects.create_user(
            username="loginuser",
            email="login@example.com",
            password="SecurePass123!",
        )
        data = {
            "username": "loginuser",
            "password": "SecurePass123!",
        }
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["username"], "loginuser")

    def test_user_login_wrong_password(self):
        _user = User.objects.create_user(
            username="badlogin",
            email="badlogin@example.com",
            password="CorrectPass123!",
        )
        data = {"username": "badlogin", "password": "WrongPass"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_unauthenticated(self):
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_profile_retrieve(self):
        user = User.objects.create_user(
            username="profileuser",
            email="profile@example.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "profileuser")
        self.assertEqual(response.data["first_name"], "John")

    def test_user_profile_update_put(self):
        user = User.objects.create_user(
            username="updateuser",
            email="update@example.com",
            password="SecurePass123!",
            first_name="Old",
        )
        self.client.force_authenticate(user=user)
        update_data = {
            "username": "updateuser",
            "email": "update@example.com",
            "first_name": "New",
            "last_name": "Name",
        }
        response = self.client.put(self.profile_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Name")

    def test_user_profile_update_patch(self):
        user = User.objects.create_user(
            username="patchuser",
            email="patch@example.com",
            password="SecurePass123!",
            first_name="Old",
        )
        self.client.force_authenticate(user=user)
        update_data = {"first_name": "New"}
        response = self.client.patch(self.profile_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "New")

    def test_user_profile_update_conflicting_email(self):
        _other = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="password",
        )
        user = User.objects.create_user(
            username="me",
            email="me@example.com",
            password="password",
        )
        self.client.force_authenticate(user=user)
        response = self.client.patch(
            self.profile_url,
            {"email": "other@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserProfileSerializerFieldsTests(TestCase):
    def test_profile_serializer_readonly_fields(self):
        user = User.objects.create_user(
            username="fcheck",
            email="fcheck@example.com",
            password="password",
            is_staff=True,
        )
        serializer = UserProfileSerializer(user)
        data = serializer.data
        for field in ("id", "is_staff", "is_superuser", "date_joined"):
            self.assertIn(field, data)
        self.assertTrue(data["is_staff"])
