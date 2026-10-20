"""Minimal JSON-over-HTTP client on the standard library."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from . import __version__, log

DEFAULT_TIMEOUT = 30.0
# The dataplane proxy forwards the caller's User-Agent upstream, and the ESDS
# Cloudflare zone bans urllib's default one (error 1010, browser_signature_banned).
USER_AGENT = f"eunomia-cli/{__version__}"


@dataclass
class Response:
    method: str
    url: str
    status: int
    body: bytes
    headers: Dict[str, str]

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            raise log.fail(f"{self.method} {self.url} -> non-JSON response\n{self.text[:800]}")


def request(
    method: str,
    url: str,
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    insecure: bool = False,
) -> Response:
    """Send a request and return the response, whatever its status.

    Connection failures (refused, timeout, DNS) abort: no caller can do
    anything useful with them except report which URL was unreachable.
    """
    data = None
    hdrs = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return Response(method, url, r.status, r.read(), dict(r.headers))
    except urllib.error.HTTPError as e:
        return Response(method, url, e.code, e.read(), dict(e.headers or {}))
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise log.fail(f"{method} {url} -> unreachable ({reason})")


def probe(url: str, timeout: float = 5.0) -> Optional[int]:
    """Status code of a GET, or None when nothing answers. Never aborts."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return None


def checked(method: str, url: str, body: Any = None, **kw: Any) -> Response:
    """Like request(), but aborts on anything that is not 2xx.

    Use it for every call that mutates state: a swallowed error there means a
    step silently did nothing while the run still reports success.
    """
    r = request(method, url, body, **kw)
    if not r.ok:
        sent = f"\nrequest:\n{json.dumps(body, indent=2, ensure_ascii=False)[:1500]}" if body is not None else ""
        raise log.fail(f"{method} {url} -> HTTP {r.status}{sent}\nresponse:\n{r.text[:1500]}")
    return r


def get_json(url: str, **kw: Any) -> Any:
    return checked("GET", url, **kw).json()


def post_json(url: str, body: Any = None, **kw: Any) -> Any:
    r = checked("POST", url, body, **kw)
    return r.json() if r.body.strip() else None
