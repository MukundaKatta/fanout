"""Tests for Supabase JWT verification in ``app.auth``."""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from app import auth, main

SECRET = "test-secret-at-least-32-bytes-long-xx"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.delenv("SUPABASE_JWT_AUDIENCE", raising=False)
    return TestClient(main.app)


def _token(**claims):
    payload = {"aud": "authenticated", **claims}
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_dev_mode_returns_fixed_user(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    res = TestClient(main.app).get("/me")
    assert res.status_code == 200
    assert res.json() == {"user_id": auth.DEV_USER_ID}


def test_empty_secret_is_dev_mode(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    assert TestClient(main.app).get("/me").json()["user_id"] == auth.DEV_USER_ID


def test_valid_token_returns_sub(client):
    res = client.get("/me", headers={"Authorization": f"Bearer {_token(sub='user-1')}"})
    assert res.status_code == 200
    assert res.json() == {"user_id": "user-1"}


def test_missing_header_is_401(client):
    res = client.get("/me")
    assert res.status_code == 401
    assert "Missing bearer" in res.json()["detail"]


@pytest.mark.parametrize("header", ["Token abc", "Bearer", "Bearer a b"])
def test_malformed_header_is_401(client, header):
    assert client.get("/me", headers={"Authorization": header}).status_code == 401


def test_bad_signature_is_401(client):
    bad = jwt.encode({"aud": "authenticated", "sub": "u"}, "another-secret-32-bytes-long-xxxxxx", algorithm="HS256")
    res = client.get("/me", headers={"Authorization": f"Bearer {bad}"})
    assert res.status_code == 401
    assert "Invalid token" in res.json()["detail"]


def test_wrong_audience_is_401(client):
    tok = jwt.encode({"aud": "anon", "sub": "u"}, SECRET, algorithm="HS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_custom_audience_env(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "custom")
    tok = jwt.encode({"aud": "custom", "sub": "u2"}, SECRET, algorithm="HS256")
    res = client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.json() == {"user_id": "u2"}


def test_token_without_sub_is_401(client):
    res = client.get("/me", headers={"Authorization": f"Bearer {_token()}"})
    assert res.status_code == 401
    assert "sub" in res.json()["detail"]


def test_users_are_isolated(client, monkeypatch):
    """Drafts created by one JWT user are invisible to another."""
    from app import store

    store.save_variations("alice", "product text", "x", [{"angle": "a", "content": "hi"}])
    alice = {"Authorization": f"Bearer {_token(sub='alice')}"}
    bob = {"Authorization": f"Bearer {_token(sub='bob')}"}
    assert len(client.get("/drafts", headers=alice).json()) == 1
    assert client.get("/drafts", headers=bob).json() == []
