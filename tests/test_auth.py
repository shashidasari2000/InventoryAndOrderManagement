from fastapi.testclient import TestClient
from unittest.mock import patch


def test_register_user(client: TestClient):
    with patch("app.services.auth_service.send_otp", return_value=True):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "phone_number": "+919876543210",
                "business_name": "Test Kirana Store",
                "gst_number": None,
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["phone_number"] == "+919876543210"


def test_verify_otp_invalid(client: TestClient):
    resp = client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": "+919876543210", "otp": "000000"},
    )
    assert resp.status_code == 400


def test_register_and_verify(client: TestClient):
    phone = "+919000000001"
    with patch("app.services.auth_service.send_otp", return_value=True):
        client.post(
            "/api/v1/auth/register",
            json={"phone_number": phone, "business_name": "My Shop"},
        )

    from app.services.auth_service import generate_otp, hash_otp
    from app.database import SessionLocal
    from app.models.otp import OTPRecord
    from datetime import datetime, timedelta

    otp = "123456"
    with patch("app.services.auth_service.generate_otp", return_value=otp):
        with patch("app.services.auth_service.send_otp", return_value=True):
            client.post("/api/v1/auth/request-otp", json={"phone_number": phone})

    resp = client.post(
        "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": otp}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
