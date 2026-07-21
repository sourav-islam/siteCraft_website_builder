from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


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

    def test_user_login_success(self):
        user = User.objects.create_user(
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

    def test_user_profile_retrieve(self):
        user = User.objects.create_user(
            username="profileuser",
            email="profile@example.com",
            password="SecurePass123!",
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "profileuser")

    def test_user_profile_update(self):
        user = User.objects.create_user(
            username="updateuser",
            email="update@example.com",
            password="SecurePass123!",
            first_name="Old",
        )
        self.client.force_authenticate(user=user)
        update_data = {
            "first_name": "New",
        }
        response = self.client.patch(self.profile_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "New")
