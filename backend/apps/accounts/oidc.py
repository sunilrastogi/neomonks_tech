"""Minimal per-tenant OIDC (Authorization Code flow).

Each tenant configures its own IdP via ``OrgSSOConfig``, so the client
credentials are dynamic — we drive the standard discovery → authorize →
token → userinfo flow with ``requests`` rather than a statically-registered
OAuth client. The network functions are kept small so they can be mocked in
tests; ``provision_user`` is pure and unit-tested directly.
"""
from __future__ import annotations

from urllib.parse import urlencode

import requests

from apps.accounts.models import AuthSource, User

_SCOPE = "openid email profile"


class SSOError(Exception):
    pass


class SSODomainNotAllowed(SSOError):
    pass


def fetch_discovery(discovery_url: str) -> dict:
    resp = requests.get(discovery_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def build_authorize_url(cfg, redirect_uri: str, state: str, nonce: str) -> str:
    doc = fetch_discovery(cfg.discovery_url)
    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _SCOPE,
        "state": state,
        "nonce": nonce,
        "response_mode": "query",
    }
    return f"{doc['authorization_endpoint']}?{urlencode(params)}"


def exchange_code(cfg, code: str, redirect_uri: str) -> dict:
    doc = fetch_discovery(cfg.discovery_url)
    resp = requests.post(
        doc["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(cfg, access_token: str) -> dict:
    doc = fetch_discovery(cfg.discovery_url)
    resp = requests.get(
        doc["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def email_from_claims(claims: dict) -> str:
    return (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").strip().lower()


def provision_user(cfg, claims: dict) -> User:
    """Match an SSO identity to a tenant user, creating one if allowed.

    Raises SSOError / SSODomainNotAllowed on policy violations.
    """
    email = email_from_claims(claims)
    if not email:
        raise SSOError("No email claim returned by the identity provider.")

    domains = cfg.allowed_domains_list()
    if domains and email.split("@")[-1] not in domains:
        raise SSODomainNotAllowed(f"Email domain not permitted for SSO: {email}")

    user = User.objects.filter(email=email).first()
    if user is None:
        if not cfg.auto_provision:
            raise SSOError("User does not exist and auto-provisioning is disabled.")
        user = User(
            email=email,
            full_name=claims.get("name", "") or "",
            role=cfg.default_role,
            auth_source=AuthSource.SSO,
            is_active=True,
        )
        user.set_unusable_password()
        user.save()
    return user
