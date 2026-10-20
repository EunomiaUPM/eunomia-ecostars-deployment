"""Pinned images and, with --check, what the registries hold beyond them.

A newer tag is reported, never applied: the fafnir and heimdall repositories
on Docker Hub carry test builds with no published source (v0.3.test, v2.2.test),
so picking a tag stays a human decision.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from .. import http, log, settings

IMAGE_RE = re.compile(r"^\s*image:\s*['\"]?([^'\"\s]+)['\"]?\s*$")


def pinned(env: str) -> Dict[str, Set[str]]:
    """image reference -> compose files that use it."""
    found: Dict[str, Set[str]] = {}
    for stack in settings.stacks(env).values():
        if not stack.compose.is_file():
            continue
        for line in stack.compose.read_text().splitlines():
            m = IMAGE_RE.match(line)
            if m:
                found.setdefault(m.group(1), set()).add(stack.compose.name)
    return found


def _split(ref: str) -> Tuple[str, str, str]:
    """(registry, repository, tag)."""
    name, _, tag = ref.rpartition(":") if ":" in ref.split("/")[-1] else (ref, "", "")
    if "/" in name and ("." in name.split("/")[0] or ":" in name.split("/")[0]):
        registry, repo = name.split("/", 1)
    else:
        registry, repo = "docker.io", name if "/" in name else f"library/{name}"
    return registry, repo, tag


def _tags(registry: str, repo: str) -> Optional[List[Tuple[str, datetime]]]:
    """Tags with their push date, newest first; None if the registry is not supported."""
    if registry == "quay.io":
        r = http.request("GET", f"https://quay.io/api/v1/repository/{repo}/tag/?limit=50&onlyActiveTags=true")
        if not r.ok:
            return None
        return sorted(
            ((t["name"], datetime.fromtimestamp(t["start_ts"], timezone.utc)) for t in r.json().get("tags", [])),
            key=lambda t: t[1],
            reverse=True,
        )
    if registry == "docker.io":
        r = http.request("GET", f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=50&ordering=last_updated")
        if not r.ok:
            return None
        out = []
        for t in r.json().get("results", []):
            # e.g. 2026-06-30T17:06:21.262378Z; fromisoformat on 3.8 rejects
            # both the Z and the microseconds, so keep the seconds only.
            stamp = (t.get("last_updated") or "")[:19]
            if stamp:
                out.append((t["name"], datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)))
        return out
    return None


def show(env: str, check: bool) -> int:
    images = pinned(env)
    for ref in sorted(images):
        registry, repo, tag = _split(ref)
        files = ", ".join(sorted(images[ref]))
        unpinned = "  (no tag: resolves to latest)" if not tag else ""
        print(f"{ref}{unpinned}\n    used in {files}")
        if not check or not tag:
            continue
        if repo.startswith("library/"):
            # Official images rebuild every tag constantly, so push dates say
            # nothing about what is newer.
            print("    (official image: not checked)")
            continue
        tags = _tags(registry, repo)
        if tags is None:
            print("    (registry not queried)")
            continue
        current = next((d for n, d in tags if n == tag), None)
        if current is None:
            print(f"    tag {tag} not found in the registry")
            continue
        newer = [f"{n} ({d:%Y-%m-%d})" for n, d in tags if d > current and n != tag]
        print(f"    pinned {tag} ({current:%Y-%m-%d})" + (f"; newer: {', '.join(newer)}" if newer else "; up to date"))
    if check:
        log.info("\nNewer tags are reported, never applied. Check their source before bumping a pin.")
    return 0
