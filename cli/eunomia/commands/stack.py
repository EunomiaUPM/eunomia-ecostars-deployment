"""Stack lifecycle: up, down, status, logs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Sequence

from .. import compose, http, log, settings
from ..settings import CONTAINER_PREFIX, DATASPACE_NODES, REPO_ROOT, Stack
from . import catalog, onboard


def resolve_nodes(requested: Sequence[str]) -> List[str]:
    """`all` adds the client stack to the dataspace; no args means the dataspace."""
    if not requested:
        return list(DATASPACE_NODES)
    if "all" in requested:
        return list(settings.ALL_NODES)
    # Keep the dependency order whatever order they were typed in.
    return [n for n in settings.ALL_NODES if n in requested]


def _check_client_checkout() -> None:
    inner = settings.CLIENT_DIR / "inner" / "ingestion-service"
    if not inner.is_dir():
        raise log.fail(
            "The consumer client stack is a git submodule that is not checked out. Run:\n"
            "  git submodule update --init services/consumer-client-stack/inner"
        )


# ---------------------------------------------------------------------------
# up
# ---------------------------------------------------------------------------


def up(env: str, nodes: Sequence[str], onboarding: bool, populate: bool, pull: bool) -> None:
    compose.require("docker", "Install Docker Desktop or the Docker engine with the compose plugin.")
    targets = resolve_nodes(nodes)
    all_stacks = settings.stacks(env)
    chosen = [all_stacks[n] for n in targets]

    if env == "standalone":
        squatters = compose.foreign_listeners(p for s in chosen for p in s.ports)
        if squatters:
            raise log.fail(
                "These ports are held by non-Docker processes. Stop them first, or the\n"
                "agents will look healthy while 127.0.0.1 reaches the stray process:\n" + "\n".join(squatters)
            )
    if "client" in targets:
        _check_client_checkout()

    for stack in chosen:
        log.step(f"Starting {stack.node}")
        if pull:
            compose.compose(stack, "pull", "--ignore-buildable")
        args = ["up", "-d", "--wait", "--remove-orphans"]
        if stack.node == "client":
            # The ingestion service is built from the submodule; Docker's layer
            # cache makes this a no-op when nothing moved.
            args.append("--build")
        compose.compose(stack, *args)

    urls = {s.node: settings.node_url(env, s.node) for s in chosen if s.node != "client"}
    log.step("Checking readiness from this host")
    for stack in chosen:
        if stack.readiness:
            compose.wait_http(stack.node.capitalize(), f"{urls[stack.node]}{stack.readiness}")

    whole_dataspace = all(n in targets for n in DATASPACE_NODES)
    if env == "prod":
        # In prod each participant lives on its own server, so cross-node
        # steps are run once all of them are up, from anywhere.
        log.info("\nProd: run `eunomia onboard --env prod` and `eunomia catalog populate --env prod` once every node is up.")
    else:
        ep = settings.endpoints(env)
        if onboarding and whole_dataspace:
            onboard.run_all(ep)
        elif onboarding:
            log.info("Onboarding skipped: it needs authority, provider and consumer up together")
        if populate and "provider" in targets:
            esds = settings.esds(required=False)
            if esds is None:
                log.warn(
                    f"catalog not populated: no ESDS credentials in "
                    f"{settings.ESDS_ENV_FILE.relative_to(REPO_ROOT)}. Then run: eunomia catalog populate"
                )
            else:
                catalog.populate(ep.provider, esds)

    lines = [f"  {node:<10} {url}{'/admin/home' if node == 'authority' else '/admin/login'}" for node, url in urls.items()]
    if "client" in targets:
        lines.append("  client     http://127.0.0.1:8000/docs  ·  Metabase http://127.0.0.1:3000")
    log.ok(f"\n{env.capitalize()} deployment ready:\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# down
# ---------------------------------------------------------------------------


def _wipe_vault(dry_run: bool) -> None:
    """Remove the identity material the setup jobs generate under vault/.

    The DIDs, keys and wallet state live in vault/ through a bind mount, not
    in a Docker volume, so `down -v` leaves them behind and a redeploy would
    silently reuse the old identities. Only generated files go: vault/ also
    holds committed .example files the deployment needs to boot.
    """
    if shutil.which("git") and (REPO_ROOT / ".git").exists():
        # git knows which files are committed, so it draws the line. -x
        # includes ignored files, which is where the generated keys live.
        # LC_ALL=C because the "Would remove" prefix is translated otherwise.
        res = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "clean", "-ndx", "--", "vault/"],
            capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"},
        )
        pending = [line.replace("Would remove ", "  ") for line in res.stdout.splitlines()]
        if not pending:
            log.ok("vault/ is already clean")
            return
        print("\n".join(pending), file=sys.stderr)
        compose.run(["git", "-C", str(REPO_ROOT), "clean", "-fdx", "--", "vault/"], dry_run=dry_run, capture=True)
        log.ok("Generated identity material " + ("would be removed" if dry_run else "removed"))
        return

    # Not a git checkout (a copied directory, say): fall back to the names the
    # setup jobs are known to generate.
    log.info("Not a git checkout, removing the known generated files")
    for node in ("consumer", "provider", "heimdall"):
        secrets = settings.VAULT_DIR / node / "secrets"
        for name in ("cert.json.example", "private_key.json.example", "public_key.json.example"):
            target = secrets / name
            if target.is_file():
                compose.run(["rm", "-f", str(target)], dry_run=dry_run)
    log.ok("Generated identity material " + ("would be removed" if dry_run else "removed"))


def down(yes: bool, dry_run: bool, images: bool, keep_identities: bool, client: bool) -> None:
    compose.require("docker")
    stacks = settings.stacks("standalone")
    order = (["client"] if client else []) + ["consumer", "provider", "authority"]

    if not dry_run and not yes:
        log.info("This removes the whole standalone deployment:")
        log.info(f"  · every {CONTAINER_PREFIX}* container, network and volume")
        log.info("  · the catalog and every negotiated agreement (they live in the databases)")
        if not keep_identities:
            log.info("  · the generated identities in vault/: the agents get new DIDs")
        if client:
            log.info("  · the client stack and its volume (ingested data and Metabase dashboards)")
        if images:
            log.info("  · the locally built images")
        if not sys.stdin.isatty():
            raise log.fail("Not running interactively. Re-run with --yes to confirm, or --dry-run to preview.")
        if input("Type 'yes' to continue: ").strip() != "yes":
            raise log.fail("Aborted, nothing was removed.")
    if dry_run:
        log.info("DRY RUN: nothing will actually be removed")

    log.step("Step 1 · Stopping the stacks")
    for node in order:
        stack = stacks[node]
        args = ["down", "--volumes", "--remove-orphans"] + (["--rmi", "local"] if images else [])
        log.info(f"down: {node}")
        compose.compose(stack, *args, dry_run=dry_run)

    log.step("Step 2 · Sweeping stray containers and networks")
    # Anything started outside compose, or left by an interrupted run, is
    # invisible to `down` but still holds its name and port.
    if dry_run:
        # Nothing was brought down, so every container would look stray here.
        log.info(f"would remove any {CONTAINER_PREFIX}* container or network still left after step 1")
    else:
        _sweep()

    log.step("Step 3 · Generated state in vault/")
    if keep_identities:
        log.info("Keeping vault/ (--keep-identities): the agents will reuse their DIDs")
    else:
        _wipe_vault(dry_run)

    log.step("Step 4 · Checking the ports are free")
    if dry_run:
        log.info("Skipped in dry-run mode")
    else:
        ports = [p for n in order for p in stacks[n].ports]
        busy = [f"  :{p}  {line}" for p in ports for line in compose.listeners(p)]
        if busy:
            raise log.fail("Some ports are still held. Stop these before redeploying:\n" + "\n".join(busy))
        log.ok(f"All {len(ports)} ports are free")

    log.ok("\nDry run complete: nothing was removed." if dry_run else "\nTeardown complete. Redeploy with: eunomia up")


def _sweep() -> None:
    stray = compose.run(["docker", "ps", "-aq", "--filter", f"name=^/{CONTAINER_PREFIX}"], capture=True).split()
    if stray:
        compose.run(["docker", "rm", "-f", *stray], capture=True)
        log.ok(f"Removed {len(stray)} leftover container(s)")
    else:
        log.ok("No stray containers")
    nets = compose.run(["docker", "network", "ls", "-q", "--filter", f"name={CONTAINER_PREFIX}"], capture=True).split()
    if nets:
        compose.run(["docker", "network", "rm", *nets], capture=True, check=False)
        log.ok(f"Removed {len(nets)} leftover network(s)")
    else:
        log.ok("No stray networks")


# ---------------------------------------------------------------------------
# status / logs
# ---------------------------------------------------------------------------


def _containers(stack: Stack) -> List[Dict[str, str]]:
    out = compose.compose(stack, "ps", "-a", "--format", "json", capture=True, check=False).strip()
    if not out:
        return []
    # Compose prints a JSON array in older releases and JSON lines in newer ones.
    if out.startswith("["):
        return json.loads(out)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def status(env: str) -> int:
    compose.require("docker")
    healthy = True
    for node, stack in settings.stacks(env).items():
        rows = _containers(stack)
        # A prod server runs one node; the client stack is optional anywhere.
        if not rows and (node == "client" or env == "prod"):
            continue
        ready = ""
        if stack.readiness:
            if env == "prod" and not os.environ.get(f"{node.upper()}_URL"):
                ready = f"readiness unknown: {node.upper()}_URL not set"
            else:
                code = http.probe(f"{settings.node_url(env, node)}{stack.readiness}")
                ready = "ready" if code == 200 else f"not ready ({code or 'no answer'})"
                healthy &= code == 200
        print(f"\n{node}  {ready}")
        if not rows:
            print("    (no containers)")
        for c in rows:
            state = c.get("State", "")
            health = c.get("Health") or ""
            print(f"    {c.get('Name', ''):<38} {state:<9} {health}")
    return 0 if healthy else 1


def logs(env: str, node: str, follow: bool, tail: str, services: Sequence[str]) -> int:
    stack = settings.stacks(env)[node]
    args = ["logs", "--tail", tail] + (["-f"] if follow else []) + list(services)
    return subprocess.call(compose.compose_cmd(stack, *args), cwd=REPO_ROOT)
