import base64
import json

from django.test import TestCase
from rest_framework.test import APIClient

from tunisovereign_core.models import StakeholderUser

from .helpers import PASSWORD, Role, make_user


def jwt_payload(token: str) -> dict:
    body = token.split(".")[1]
    body += "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body))


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_always_creates_a_student(self):
        resp = self.client.post(
            "/api/auth/register/",
            {"username": "sneaky", "password": PASSWORD, "role": "NATIONAL_ADMIN"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(StakeholderUser.objects.get(username="sneaky").role, Role.STUDENT)
        self.assertNotIn("password", resp.data)

    def test_register_rejects_weak_password(self):
        resp = self.client.post("/api/auth/register/", {"username": "weak", "password": "123"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_login_token_contains_custom_claims(self):
        make_user("mentor", Role.MENTOR_AUDITOR, institution="ISG Tunis", wallet_address="0xabc")
        resp = self.client.post("/api/auth/login/", {"username": "mentor", "password": PASSWORD}, format="json")
        self.assertEqual(resp.status_code, 200)
        claims = jwt_payload(resp.data["access"])
        self.assertEqual(claims["role"], "MENTOR_AUDITOR")
        self.assertEqual(claims["institution"], "ISG Tunis")
        self.assertEqual(claims["wallet_address"], "0xabc")
        self.assertIn("governorate", claims)

    def test_login_wrong_password_is_401(self):
        make_user("u1")
        resp = self.client.post("/api/auth/login/", {"username": "u1", "password": "nope"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_refresh_returns_new_access_token(self):
        make_user("u2")
        tokens = self.client.post("/api/auth/login/", {"username": "u2", "password": PASSWORD}, format="json").data
        resp = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)

    def test_rbac_admin_only_endpoint(self):
        student, admin = make_user("stu"), make_user("adm", Role.NATIONAL_ADMIN)
        self.assertEqual(self.client.get("/api/auth/admin-only/").status_code, 401)
        self.client.force_authenticate(student)
        self.assertEqual(self.client.get("/api/auth/admin-only/").status_code, 403)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/auth/admin-only/").status_code, 200)

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.force_authenticate(make_user("me1"))
        resp = self.client.get("/api/auth/me/")
        self.assertEqual((resp.status_code, resp.data["role"]), (200, "STUDENT"))
