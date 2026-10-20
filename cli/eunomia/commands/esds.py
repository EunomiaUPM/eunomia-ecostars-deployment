"""ESDS connectivity check, independent of the dataspace.

Replaces services/provider-final-system/smoke_on_final_system.sh.
"""

from __future__ import annotations

import base64
import json
from typing import Optional
from urllib.parse import urlsplit

from .. import http, log
from ..settings import Esds


def _jwt_issuer(token: str) -> Optional[str]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("iss")
    except (IndexError, ValueError):
        return None


def check(esds: Esds) -> int:
    log.step(f"ESDS at {esds.api}")

    # A staging key against the production host answers 401 exactly like a
    # revoked one, so compare the key's issuer with the host before anything.
    iss = _jwt_issuer(esds.api_key)
    host = urlsplit(esds.api).hostname or ""
    if iss:
        log.info(f"API key issued by {iss}")
        if ("staging" in iss) != ("staging" in host):
            log.warn(f"the key comes from {iss} but the API host is {host}: expect 401")

    failed = False
    for endpoint in ("environmental", "social"):
        url = f"{esds.api}/{endpoint}"
        anon = http.request("GET", url, timeout=30).status
        r = http.request("GET", url, headers={"Authorization": f"Bearer {esds.api_key}"}, timeout=90)
        count = ""
        if r.ok:
            data = r.json()
            count = f", {len(data)} hotel(s)" if isinstance(data, list) else ""
        line = f"  /{endpoint:<14} with key -> {r.status}{count}   without key -> {anon}"
        if r.ok and anon == 401:
            log.ok(line)
        else:
            failed = True
            log.warn(line + ("" if r.ok else f"\n    {r.text[:300]}"))

    if failed:
        raise log.fail("ESDS check failed")
    log.ok("ESDS reachable, key accepted, anonymous access refused")
    return 0
