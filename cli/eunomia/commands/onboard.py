"""Onboarding: link wallets, get credentials from the authority, GNAP handshake.

Every step checks first and skips when already done, so the whole sequence is
safe to re-run after a redeploy.
"""

from __future__ import annotations

import time
from typing import Callable

from .. import http, log
from ..settings import Endpoints

VC_TYPE = "DataSpaceParticipant_jwt_vc_json"


def _did(base_url: str) -> str:
    return http.get_json(f"{base_url}/.well-known/did.json")["id"]


def _poll(check: Callable[[], bool], timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(1)
    return check()


def link_wallets(ep: Endpoints) -> None:
    log.step("Linking wallets")
    for node in ("authority", "consumer", "provider"):
        http.checked("POST", f"{ep.url(node)}/api/v1/wallet/link")
    log.ok("Wallets linked")


def register(ep: Endpoints, node: str) -> None:
    """Get `node` a DataSpaceParticipant credential from the authority."""
    log.step(f"Registering {node} with the authority")
    participant = ep.url(node)
    authority_did = _did(ep.authority)

    def holds_credential() -> bool:
        requests = http.get_json(f"{participant}/api/v1/vc-request/all") or []
        return any(
            r.get("participant_id") == authority_did
            and r.get("status") == "Finalized"
            and VC_TYPE in (r.get("vc_type_config") or [])
            for r in requests
        )

    # /vc-request/beg never deduplicates: every call files a fresh petition
    # with the authority, so without this guard each run piles up another one.
    if holds_credential():
        log.info(f"{node} already holds the credential, skipping")
        return

    # The field is "nick", not "slug": "slug" fails with HTTP 400
    # "Error extracting Json payload".
    http.checked(
        "POST",
        f"{participant}/api/v1/vc-request/beg",
        {
            "url": f"{ep.docker_authority}/api/v1/gate/access",
            "id": authority_did,
            "nick": "authority",
            "vc_type": VC_TYPE,
            "method": "cert",
            "auto": True,
        },
    )
    if not _poll(holds_credential):
        raise log.fail(f"{node} filed the request but the credential never reached Finalized")
    log.ok(f"{node} holds the credential")


def authenticate(ep: Endpoints, provider_nick: str = "provider") -> None:
    """GNAP handshake that mints the consumer's mate token for the provider."""
    log.step("Authenticating the consumer with the provider")
    provider_did = _did(ep.provider)

    # Check the token, not the mate: a tokenless mate row means the handshake
    # never completed, and the provider then answers 401 to every DSP call
    # (surfaced as 502 by the consumer BFF).
    def has_token() -> bool:
        mates = http.get_json(f"{ep.consumer}/api/v1/mates/all") or []
        return any(m.get("participant_id") == provider_did and (m.get("token") or "") for m in mates)

    if has_token():
        log.info("The consumer is already authenticated with the provider, skipping")
        return

    # POST /api/v1/mates is NOT equivalent: it only inserts the row. The
    # payload is ReachProvider (ds-agent crates/auth/src/types/entities/reacher.rs);
    # actions accepts "talk" and "request-vc".
    http.checked(
        "POST",
        f"{ep.consumer}/api/v1/peer-connection/connect",
        {
            "id": provider_did,
            "nick": provider_nick,
            "url": f"{ep.docker_provider}/api/v1/gate/access",
            "actions": ["talk"],
            "auto": True,
        },
    )
    if not _poll(has_token):
        raise log.fail("The handshake was accepted but the consumer still holds no token for the provider")
    log.ok("Consumer authenticated with the provider")


def run_all(ep: Endpoints) -> None:
    link_wallets(ep)
    register(ep, "consumer")
    register(ep, "provider")
    authenticate(ep)
    log.ok("\nOnboarding complete")
