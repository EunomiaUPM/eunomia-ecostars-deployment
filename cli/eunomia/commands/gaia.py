"""GAIA-X credential flow for the consumer: legal VC, self-attested VCs, label VC.

Ported from scripts/gaia.sh with the API changes of the Fafnir-generation
agents applied (the bash version predates them and no longer worked):
"slug" is now "nick", /onboard/provider is /peer-connection/connect, and
/gaia/credential/generate is /gaia/generate.

The authority must be able to issue the gx_* credential types, which the
standalone DataSpaceAuthority role is not configured for.
"""

from __future__ import annotations

from .. import http, log
from ..settings import Endpoints
from . import onboard


def _beg(ep: Endpoints, authority_did: str, vc_type: str, method: str) -> None:
    http.checked(
        "POST",
        f"{ep.consumer}/api/v1/vc-request/beg",
        {
            "url": f"{ep.docker_authority}/api/v1/gate/access",
            "id": authority_did,
            "nick": "authority",
            "vc_type": vc_type,
            "method": method,
            "auto": True,
        },
    )


def run(ep: Endpoints) -> None:
    onboard.link_wallets(ep)

    log.step("Retrieving DIDs")
    dids = {n: http.get_json(f"{ep.url(n)}/.well-known/did.json")["id"] for n in ("consumer", "provider", "authority")}
    for node, did in dids.items():
        log.info(f"{node:<9}: {did[:70]}")

    log.step("Requesting the legal VC (gx_VatId)")
    _beg(ep, dids["authority"], "gx_VatId_jwt_vc_json", "cert")

    log.step("Generating the self-attested GAIA-X VCs")
    http.checked("POST", f"{ep.consumer}/api/v1/gaia/generate")

    log.step("Requesting the label VC (gx_LabelCredential)")
    _beg(ep, dids["authority"], "gx_LabelCredential_jwt_vc_json", "oidc4vp")

    onboard.authenticate(ep)
    log.ok("\nGAIA-X flow completed")
