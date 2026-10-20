"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__, log, settings
from .commands import catalog, e2e, esds, gaia, images, onboard, restart, stack

NODES_HELP = "authority, provider, consumer, client, or all (default: the three dataspace nodes)"


def _node(value: str) -> str:
    # A type check rather than choices=: with nargs="*", argparse also checks
    # the empty default against choices and rejects a bare `eunomia up`.
    allowed = settings.ALL_NODES + ("all",)
    if value not in allowed:
        raise argparse.ArgumentTypeError(f"invalid node {value!r} (choose from {', '.join(allowed)})")
    return value


def _add_env(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--env",
        choices=settings.ENVIRONMENTS,
        default="standalone",
        help="standalone (default): every participant on this host. prod: real servers.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eunomia",
        description="Deploy, onboard and test the Ecostars dataspace.",
        epilog="Settings come from the shell and from .env at the repo root (see .env.example).",
    )
    parser.add_argument("--version", action="version", version=f"eunomia {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    p = sub.add_parser("up", help="start stacks, wait for them, onboard and populate the catalog")
    p.add_argument("nodes", nargs="*", type=_node, metavar="node", help=NODES_HELP)
    _add_env(p)
    p.add_argument("--no-onboarding", action="store_true", help="only start the stacks")
    p.add_argument("--no-catalog", action="store_true", help="do not populate the provider catalog")
    p.add_argument("--pull", action="store_true", help="pull the pinned images before starting")

    p = sub.add_parser("down", help="remove the standalone deployment, identities included")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    p.add_argument("-n", "--dry-run", action="store_true", help="show what would be removed")
    p.add_argument("--images", action="store_true", help="also remove locally built images")
    p.add_argument("--keep-identities", action="store_true", help="keep vault/, so the agents keep their DIDs")
    p.add_argument("--client", action="store_true", help="also remove the client stack and its volume")

    p = sub.add_parser("status", help="containers and readiness of every node")
    _add_env(p)

    p = sub.add_parser("logs", help="logs of one node's stack")
    p.add_argument("node", choices=settings.ALL_NODES)
    p.add_argument("services", nargs="*", help="limit to these compose services")
    _add_env(p)
    p.add_argument("-f", "--follow", action="store_true")
    p.add_argument("--tail", default="200", help="lines per container (default: 200, or 'all')")

    p = sub.add_parser("onboard", help="link wallets, register with the authority, authenticate")
    p.add_argument(
        "step",
        nargs="?",
        choices=("wallets", "register", "authenticate"),
        help="run a single step (default: all of them, in order)",
    )
    p.add_argument("node", nargs="?", choices=("provider", "consumer"), help="for register: who registers")
    _add_env(p)

    p = sub.add_parser("catalog", help="provider catalog")
    csub = p.add_subparsers(dest="action", metavar="<action>")
    csub.required = True
    cp = csub.add_parser("populate", help="create the ECOSTARS datasets, policies and connectors")
    cp.add_argument("--force", action="store_true", help="create them again even if they exist")
    _add_env(cp)
    cs = csub.add_parser("show", help="list datasets, distributions and connector instances")
    _add_env(cs)

    p = sub.add_parser("e2e", help="negotiate, transfer and pull data end to end")
    _add_env(p)
    p.add_argument("--dataset", help=f"substring of the dataset title (default: {e2e.DEFAULT_DATASET!r})")
    p.add_argument("--list-datasets", action="store_true", help="list the catalog and exit")
    p.add_argument("--keep-open", action="store_true", help="leave the transfer STARTED")
    p.add_argument("--no-suspend", action="store_true", help="skip the suspend/resume leg")
    p.add_argument("--no-data-pull", action="store_true", help="skip the data pull through the proxy")
    p.add_argument("-v", "--verbose", action="store_true", help="dump every request and response")

    p = sub.add_parser("restart", help="restart prod nodes on their servers over SSH")
    p.add_argument("nodes", nargs="+", choices=settings.ALL_NODES + ("all",), metavar="node", help=NODES_HELP)
    p.add_argument("-n", "--dry-run", action="store_true", help="print the SSH commands instead")
    p.add_argument("-y", "--yes", action="store_true", help="confirm restarting the client stack (wipes it)")

    p = sub.add_parser("gaia", help="GAIA-X credential flow for the consumer")
    _add_env(p)

    p = sub.add_parser("images", help="pinned images; --check looks for newer tags")
    _add_env(p)
    p.add_argument("--check", action="store_true", help="query the registries")

    p = sub.add_parser("esds", help="ECOSTARS ESDS backend")
    esub = p.add_subparsers(dest="action", metavar="<action>")
    esub.required = True
    esub.add_parser("check", help="key accepted, anonymous access refused")

    return parser


def dispatch(args: argparse.Namespace) -> int:
    cmd = args.command
    if cmd == "up":
        stack.up(args.env, args.nodes, not args.no_onboarding, not args.no_catalog, args.pull)
    elif cmd == "down":
        stack.down(args.yes, args.dry_run, args.images, args.keep_identities, args.client)
    elif cmd == "status":
        return stack.status(args.env)
    elif cmd == "logs":
        return stack.logs(args.env, args.node, args.follow, args.tail, args.services)
    elif cmd == "onboard":
        ep = settings.endpoints(args.env)
        if args.step is None:
            onboard.run_all(ep)
        elif args.step == "wallets":
            onboard.link_wallets(ep)
        elif args.step == "register":
            for node in [args.node] if args.node else ["consumer", "provider"]:
                onboard.register(ep, node)
        else:
            onboard.authenticate(ep)
    elif cmd == "catalog":
        ep = settings.endpoints(args.env)
        if args.action == "populate":
            catalog.populate(ep.provider, settings.esds(), force=args.force)
        else:
            catalog.show(ep.provider)
    elif cmd == "e2e":
        return e2e.run(
            settings.endpoints(args.env),
            settings.esds(required=False),
            dataset=args.dataset,
            list_datasets=args.list_datasets,
            suspend=not args.no_suspend,
            data_pull=not args.no_data_pull,
            keep_open=args.keep_open,
            verbose=args.verbose,
        )
    elif cmd == "restart":
        return restart.restart(args.nodes, args.dry_run, args.yes)
    elif cmd == "gaia":
        gaia.run(settings.endpoints(args.env))
    elif cmd == "images":
        return images.show(args.env, args.check)
    elif cmd == "esds":
        return esds.check(settings.esds())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not settings.DEPLOYMENT_DIR.is_dir():
        # The CLI drives the compose files and payloads of its own checkout.
        log.fail(f"No deployment/ next to {settings.REPO_ROOT}. Run ./eunomia from the repo, or pip install -e .")
        return 1
    settings.load_env()
    try:
        return dispatch(args)
    except log.Abort:
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
