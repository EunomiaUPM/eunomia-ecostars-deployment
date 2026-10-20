"""docker compose and host-level helpers."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Iterable, List, Optional, Sequence

from . import http, log
from .settings import REPO_ROOT, Stack


def require(binary: str, hint: str = "") -> None:
    if shutil.which(binary) is None:
        raise log.fail(f"{binary} not found in PATH. {hint}".rstrip())


def run(cmd: Sequence[str], dry_run: bool = False, capture: bool = False, check: bool = True) -> str:
    """Run a command from the repo root. With dry_run, only print it."""
    if dry_run:
        log.info("  would run: " + " ".join(cmd))
        return ""
    res = subprocess.run(
        list(cmd),
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and res.returncode != 0:
        detail = f"\n{res.stderr.strip()}" if capture and res.stderr else ""
        raise log.fail(f"command failed ({res.returncode}): {' '.join(cmd)}{detail}")
    return res.stdout or ""


def compose_cmd(stack: Stack, *args: str) -> List[str]:
    return ["docker", "compose", "-f", str(stack.compose), *args]


def compose(stack: Stack, *args: str, dry_run: bool = False, capture: bool = False, check: bool = True) -> str:
    return run(compose_cmd(stack, *args), dry_run=dry_run, capture=capture, check=check)


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


def listeners(port: int) -> List[str]:
    """`lsof` lines for whatever listens on a TCP port, header excluded."""
    if shutil.which("lsof") is None:
        return []
    res = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], text=True, capture_output=True
    )
    return [line for line in res.stdout.splitlines()[1:] if line.strip()]


def foreign_listeners(ports: Iterable[int]) -> List[str]:
    """Listeners that are not Docker.

    A natively built agent on the same port silently wins over the container:
    Docker publishes on IPv6, those binaries bind IPv4, so 127.0.0.1:<port>
    reaches the stray process while the container looks perfectly healthy.
    """
    found = []
    for port in ports:
        for line in listeners(port):
            command = line.split()[0]
            if not command.startswith("com.docke") and command not in ("docker-pr", "vpnkit"):
                found.append(f"  :{port}  {line}")
    return found


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def wait_http(name: str, url: str, timeout: float = 180.0) -> None:
    """Poll a URL until it answers 200, or abort after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    status: Optional[int] = None
    while time.monotonic() < deadline:
        status = http.probe(url)
        if status == 200:
            log.ok(f"{name} is ready")
            return
        time.sleep(2)
    got = f"HTTP {status}" if status else "no answer"
    raise log.fail(f"{name} did not become ready at {url} ({got})")
