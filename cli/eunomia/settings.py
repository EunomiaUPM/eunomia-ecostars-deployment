"""Where things live: repo paths, stacks per environment, and participant URLs.

Two environments exist:

  standalone  all three participants on this host, fake vault, did:jwk.
  prod        one participant per server, real Vault, did:web on a domain.
              `up` runs on the target server itself; the URLs of the other
              participants come from the repo-root .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import log

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_DIR = REPO_ROOT / "deployment"
VAULT_DIR = REPO_ROOT / "vault"
CATALOG_DIR = REPO_ROOT / "static" / "catalog"
CLIENT_DIR = REPO_ROOT / "services" / "consumer-client-stack"
ESDS_ENV_FILE = REPO_ROOT / "services" / "provider-final-system" / ".env"
ENV_FILE = REPO_ROOT / ".env"
# Where the bash scripts kept their SSH settings before the move to this CLI.
LEGACY_ENV_FILE = REPO_ROOT / "scripts" / ".env"

ENVIRONMENTS = ("standalone", "prod")
DATASPACE_NODES = ("authority", "provider", "consumer")
ALL_NODES = DATASPACE_NODES + ("client",)

# Every standalone container is named ecostars-*, which is what teardown sweeps.
CONTAINER_PREFIX = "ecostars-"


@dataclass(frozen=True)
class Stack:
    node: str
    compose: Path
    # Host ports the stack publishes; checked before `up` and after `down`.
    ports: Tuple[int, ...]
    # Path appended to the node URL that answers 200 once the node is ready.
    readiness: Optional[str]
    # Agent service in the compose file, and its wallet. Used by `restart`.
    service: Optional[str] = None
    wallet: Optional[str] = None


def stacks(env: str) -> Dict[str, Stack]:
    client = Stack(
        "client",
        CLIENT_DIR / "docker-compose.nonifi.yaml",
        (8000, 5440, 3000),
        None,
    )
    if env == "standalone":
        d = DEPLOYMENT_DIR / "standalone"
        return {
            "authority": Stack(
                "authority",
                d / "docker-compose.standalone.heimdall.yaml",
                (1500, 1450),
                "/readiness",
                "heimdall",
                "heimdall-fafnir-wallet",
            ),
            "provider": Stack(
                "provider",
                d / "docker-compose.standalone.provider.yaml",
                (1200, 1400, 6379),
                "/api/v1/readiness",
                "provider",
                "provider-fafnir-wallet",
            ),
            "consumer": Stack(
                "consumer",
                d / "docker-compose.standalone.consumer.yaml",
                (1100, 1300, 6380),
                "/api/v1/readiness",
                "consumer",
                "consumer-fafnir-wallet",
            ),
            "client": client,
        }
    d = DEPLOYMENT_DIR / "prod"
    return {
        "authority": Stack(
            "authority",
            d / "docker-compose.heimdall.yaml",
            (443, 8443, 8200),
            "/readiness",
            "heimdall",
            "heimdall-fafnir-wallet",
        ),
        "provider": Stack(
            "provider",
            d / "docker-compose.provider.yaml",
            (443, 8200),
            "/api/v1/readiness",
            "provider",
            "provider-fafnir-wallet",
        ),
        "consumer": Stack(
            "consumer",
            d / "docker-compose.consumer.yaml",
            (443, 8200),
            "/api/v1/readiness",
            "consumer",
            "consumer-fafnir-wallet",
        ),
        "client": client,
    }


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def parse_dotenv(text: str) -> Dict[str, str]:
    """Parse KEY=VALUE lines the way the bash scripts did.

    Quoted values are taken verbatim. In unquoted ones a ' #' starts an inline
    comment, but a bare '#' is kept so passwords containing it survive.
    """
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            for marker in (" #", "\t#"):
                if marker in value:
                    value = value.split(marker, 1)[0].rstrip()
        out[key] = value
    return out


def load_env() -> None:
    """Load the repo-root .env into os.environ without overriding the shell."""
    source = ENV_FILE
    if not source.is_file() and LEGACY_ENV_FILE.is_file():
        log.warn(f"reading {LEGACY_ENV_FILE.relative_to(REPO_ROOT)}; move it to .env at the repo root")
        source = LEGACY_ENV_FILE
    if not source.is_file():
        return
    for key, value in parse_dotenv(source.read_text()).items():
        os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Participant URLs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Endpoints:
    """How to reach each participant.

    The plain URLs are how this process reaches the agents. The docker_* ones
    are how the agents reach each other: those travel inside DSP and GNAP
    messages, so in standalone 127.0.0.1 there would point a container at
    itself. In prod both are the public URL.
    """

    authority: str
    provider: str
    consumer: str
    docker_authority: str
    docker_provider: str
    docker_consumer: str

    def url(self, node: str) -> str:
        return getattr(self, node)


_STANDALONE_DEFAULTS = {
    "AUTHORITY_URL": "http://127.0.0.1:1500",
    "PROVIDER_URL": "http://127.0.0.1:1200",
    "CONSUMER_URL": "http://127.0.0.1:1100",
    "DOCKER_AUTHORITY_URL": "http://host.docker.internal:1500",
    "DOCKER_PROVIDER_URL": "http://host.docker.internal:1200",
    "DOCKER_CONSUMER_URL": "http://host.docker.internal:1100",
}


def node_url(env: str, node: str) -> str:
    """One participant's URL. Unlike endpoints(), needs only that node's setting."""
    name = f"{node.upper()}_URL"
    if env == "standalone":
        return (os.environ.get(name) or _STANDALONE_DEFAULTS[name]).rstrip("/")
    value = os.environ.get(name)
    if not value:
        raise log.fail(f"{name} is not set. Prod has no default URLs: add it to .env.")
    return value.rstrip("/")


def endpoints(env: str) -> Endpoints:
    def pick(name: str, fallback: Optional[str] = None) -> str:
        value = os.environ.get(name) or fallback
        if not value:
            raise log.fail(f"{name} is not set. Prod has no default URLs: add it to .env.")
        return value.rstrip("/")

    if env == "standalone":
        return Endpoints(*(pick(k, v) for k, v in _STANDALONE_DEFAULTS.items()))

    authority, provider, consumer = (pick(f"{n}_URL") for n in ("AUTHORITY", "PROVIDER", "CONSUMER"))
    return Endpoints(
        authority,
        provider,
        consumer,
        pick("DOCKER_AUTHORITY_URL", authority),
        pick("DOCKER_PROVIDER_URL", provider),
        pick("DOCKER_CONSUMER_URL", consumer),
    )


# ---------------------------------------------------------------------------
# ESDS (the Ecostars provider backend)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Esds:
    api: str
    api_key: str


def esds(required: bool = True) -> Optional[Esds]:
    """ESDS base URL and key, from the shell or services/provider-final-system/.env."""
    file_values = parse_dotenv(ESDS_ENV_FILE.read_text()) if ESDS_ENV_FILE.is_file() else {}
    api = os.environ.get("ESDS_API") or file_values.get("API")
    key = os.environ.get("ESDS_API_KEY") or file_values.get("API_KEY")
    if api and key:
        return Esds(api.rstrip("/"), key)
    if required:
        raise log.fail(
            f"No ESDS credentials. Create {ESDS_ENV_FILE.relative_to(REPO_ROOT)} with API= and API_KEY=,\n"
            "or export ESDS_API and ESDS_API_KEY."
        )
    return None
