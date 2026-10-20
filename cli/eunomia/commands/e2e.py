"""End-to-end test: DSP contract negotiation, transfer, and a real data pull.

Assumes the deployment is up, onboarded and its catalog populated, which is
what `eunomia up` leaves behind. It checks those preconditions first and
names the missing one, instead of failing later with an opaque 502.

  Discovery     participant DIDs, consumer<->provider token, callback path,
                catalog request
  Negotiation   REQUESTED -> OFFERED -> REQUESTED -> OFFERED -> ACCEPTED
                -> AGREED -> VERIFIED -> FINALIZED -> agreement id
  Transfer      REQUESTED -> STARTED -> dataplane address
  Data          GET through the dataplane proxy: must return the ESDS hotel
                list, while the same ESDS URL without a token returns 401.
                Together that proves the provider injected the API key
                server-side and the consumer never saw it.
  Lifecycle     SUSPENDED -> STARTED -> COMPLETED

The state is asserted at every step, so a call that answers 200 with an
embedded DSP rejection still fails the test.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from .. import http, log
from ..settings import Endpoints, Esds

DEFAULT_DATASET = "Environmental"
VERBOSE = False


def _dump(label: str, payload: Any) -> None:
    if VERBOSE:
        log.info(f"  {label}: {json.dumps(payload, indent=2, ensure_ascii=False)}")


def _dig(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _rpc(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _dump(f"-> {url}", payload)
    body = http.post_json(url, payload, timeout=60) or {}
    _dump("<-", body)
    return body


def _expect_state(body: Dict[str, Any], url: str, *accepted: str) -> str:
    """The state sits under different keys depending on the answer's shape."""
    state = (
        _dig(body, "response", "state")
        or _dig(body, "negotiationAgentModel", "state")
        or _dig(body, "transferAgentModel", "state")
        or _dig(body, "state")
    )
    pretty = json.dumps(body, indent=2, ensure_ascii=False)[:1500]
    if state is None:
        raise log.fail(f"{url}: no state in response\n{pretty}")
    short = state.rsplit(":", 1)[-1].upper()
    if short not in {s.upper() for s in accepted}:
        raise log.fail(f"{url}: expected {' or '.join(accepted)}, got {state}\n{pretty}")
    return short


def _pick_dataset(datasets: List[Dict[str, Any]], wanted: str, is_default: bool) -> Dict[str, Any]:
    """Datasets without a policy cannot be negotiated, so they are never candidates."""
    usable = [d for d in datasets if d.get("hasPolicy")]
    if not usable:
        raise log.fail("The catalog has no dataset with a policy. Run: eunomia catalog populate")
    needle = wanted.casefold()
    for d in usable:
        if needle in (d.get("title") or "").casefold() or needle in d.get("@id", "").casefold():
            return d
    if not is_default:
        titles = "\n".join(f"  - {d.get('title')}" for d in usable)
        raise log.fail(f"No dataset matches {wanted!r}. Available:\n{titles}")
    log.info(f"No dataset matches the default {wanted!r}, using the first one")
    return usable[0]


def _offer(policy: Dict[str, Any], target: str) -> Dict[str, Any]:
    """Echo the offer exactly as the catalog advertises it.

    Inventing permissions here would measure the agents' tolerance for
    mismatched offers instead of the real negotiation.
    """
    return {
        "@id": policy["@id"],
        "@type": "Offer",
        "target": target,
        "permission": policy.get("permission") or [],
        "obligation": policy.get("obligation") or [],
        "prohibition": policy.get("prohibition") or [],
    }


def _pull_format(dataset: Dict[str, Any]) -> str:
    """HTTP_PULL if the dataset offers it: the data check needs a pull transfer."""
    formats = []
    for dist in dataset.get("distribution") or []:
        fmt = dist.get("formats") or dist.get("format") or dist.get("dctFormats")
        if fmt:
            formats.append(fmt)
    return "HTTP_PULL" if "HTTP_PULL" in formats or not formats else formats[0]


def _rewrite_authority(url: str, reachable_base: str) -> str:
    """Point an agent-minted URL at the address this process can reach."""
    p, b = urlsplit(url), urlsplit(reachable_base)
    return urlunsplit((b.scheme, b.netloc, p.path, p.query, p.fragment))


def _find_dataplane_url(body: Any) -> Optional[str]:
    """The data address is nested differently across agent versions; scan for it."""
    found: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                if isinstance(value, str) and "dataplane" in value:
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(body)
    return found[0] if found else None


def _check_data(proxy_url: str, esds: Optional[Esds], dataset_title: str) -> None:
    log.step("Step 5 · Pulling data through the dataplane proxy")
    log.info(f"GET {proxy_url}")
    r = http.request("GET", proxy_url, timeout=90)
    if not r.ok:
        hint = ""
        if '"error_code":1010' in r.text:
            # The proxy forwards the caller's User-Agent, and the ESDS
            # Cloudflare zone bans generic client ones (urllib, python-requests).
            hint = "\nCloudflare rejected the User-Agent the proxy forwarded. Send a custom one."
        raise log.fail(f"Dataplane proxy -> HTTP {r.status}\n{r.text[:800]}{hint}")
    data = r.json()
    # ESDS answers with the full hotel list as a JSON array; an object here is
    # an error envelope forwarded by the proxy.
    if not isinstance(data, list):
        raise log.fail(f"Expected the ESDS hotel list (a JSON array), got:\n{r.text[:800]}")
    if not data:
        raise log.fail("ESDS returned an empty hotel list through the proxy")
    first = data[0] if isinstance(data[0], dict) else {}
    log.ok(f"Dataplane proxy -> HTTP {r.status}, {len(data)} hotel(s), {len(r.body)} bytes")
    if first:
        log.info(f"      first entry keys: {', '.join(sorted(first)[:8])}")

    # The positive half proves the proxy forwards. The negative half proves
    # the key was injected by the provider: the same upstream refuses us.
    if esds is None:
        log.info("      No ESDS URL configured, so the anonymous 401 check was skipped")
        return
    endpoint = "social" if "social" in dataset_title.casefold() else "environmental"
    direct = f"{esds.api}/{endpoint}"
    status = http.request("GET", direct, timeout=30).status
    if status != 401:
        raise log.fail(
            f"GET {direct} without a token -> HTTP {status}, expected 401. "
            "The upstream is open, so the proxy pull proves nothing about token injection."
        )
    log.ok(f"      {direct} without a token -> 401: the provider injected the key")


def run(
    ep: Endpoints,
    esds: Optional[Esds],
    dataset: Optional[str] = None,
    list_datasets: bool = False,
    suspend: bool = True,
    data_pull: bool = True,
    keep_open: bool = False,
    verbose: bool = False,
) -> int:
    global VERBOSE
    VERBOSE = verbose
    consumer, provider = ep.consumer, ep.provider

    # -- Step 1 · Discovery ---------------------------------------------------
    log.step("Step 1 · Discovering participants")
    consumer_did = http.get_json(f"{consumer}/api/v1/mates/myself")["participant_id"]
    provider_did = http.get_json(f"{provider}/api/v1/mates/myself")["participant_id"]
    log.info(f"Consumer DID : {consumer_did[:60]}…")
    log.info(f"Provider DID : {provider_did[:60]}…")

    mates = http.get_json(f"{consumer}/api/v1/mates/all") or []
    if not any(m.get("participant_id") == provider_did and (m.get("token") or "") for m in mates):
        raise log.fail("The consumer holds no token for the provider. Run: eunomia onboard")
    log.ok("Consumer is authenticated with the provider")

    version = http.get_json(f"{consumer}/.well-known/dspace-version/2025-1")
    callback = ep.docker_consumer + version["path"]
    log.info(f"Consumer callback: {callback}")

    # -- Step 2 · Catalog -----------------------------------------------------
    log.step("Step 2 · Requesting the provider catalog")
    catalog = _rpc(
        f"{consumer}/dsp/current/catalog/rpc/setup-catalog-request",
        {"associatedAgentPeer": provider_did, "filter": [], "noCache": True},
    )
    response = catalog.get("response") or {}
    datasets = response.get("dataset") or []
    if not datasets:
        raise log.fail("The provider catalog is empty. Run: eunomia catalog populate")
    provider_dsp = _dig(response, "service", "endpointURL")
    if not provider_dsp:
        raise log.fail("The catalog response carries no service endpointURL")
    log.ok(f"Catalog returned {len(datasets)} dataset(s)")

    if list_datasets:
        for d in datasets:
            print(f"{d['@id']}\t{len(d.get('hasPolicy') or [])} policy(ies)\t{d.get('title')}")
        return 0

    chosen = _pick_dataset(datasets, dataset or DEFAULT_DATASET, dataset is None)
    target = chosen["@id"]
    policy = chosen["hasPolicy"][0]
    offer = _offer(policy, target)
    fmt = _pull_format(chosen)
    title = chosen.get("title") or target
    log.info(f"Dataset  : {title}")
    log.info(f"Target   : {target}")
    log.info(f"Policy   : {policy['@id']}")
    log.info(f"Provider : {provider_dsp}")
    log.info(f"Format   : {fmt}")

    # -- Step 3 · Negotiation -------------------------------------------------
    log.step("Step 3 · Contract negotiation")
    url = f"{consumer}/dsp/current/negotiations/rpc/setup-request-init"
    body = _rpc(
        url,
        {
            "associatedAgentPeer": provider_did,
            "providerAddress": provider_dsp,
            "callbackAddress": callback,
            "offer": offer,
        },
    )
    pids = {"consumerPid": _dig(body, "response", "consumerPid"), "providerPid": _dig(body, "response", "providerPid")}
    if not all(pids.values()):
        raise log.fail(f"setup-request-init returned no PIDs\n{json.dumps(body, indent=2)[:1500]}")
    _expect_state(body, url, "REQUESTED")
    log.ok(f"  1/8 REQUESTED  consumerPid={pids['consumerPid']} providerPid={pids['providerPid']}")

    steps = (
        (provider, "setup-offer", {"offer": offer}, "OFFERED", "2/8 OFFERED    (provider)"),
        (consumer, "setup-request", {"offer": offer}, "REQUESTED", "3/8 REQUESTED  (consumer)"),
        (provider, "setup-offer", {"offer": offer}, "OFFERED", "4/8 OFFERED    (provider, final terms)"),
        (consumer, "setup-acceptance", {}, "ACCEPTED", "5/8 ACCEPTED   (consumer)"),
        (provider, "setup-agreement", {}, "AGREED", "6/8 AGREED     (provider)"),
        (consumer, "setup-verification", {}, "VERIFIED", "7/8 VERIFIED   (consumer)"),
    )
    for base, rpc_name, extra, state, label in steps:
        url = f"{base}/dsp/current/negotiations/rpc/{rpc_name}"
        _expect_state(_rpc(url, {**pids, **extra}), url, state)
        log.ok(f"  {label}")

    url = f"{provider}/dsp/current/negotiations/rpc/setup-finalization"
    body = _rpc(url, pids)
    _expect_state(body, url, "FINALIZED")
    agreement = _dig(body, "negotiationAgentModel", "agreement", "id") or _dig(body, "response", "agreement", "@id")
    if not agreement:
        raise log.fail(f"Finalization carried no agreement id\n{json.dumps(body, indent=2)[:1500]}")
    log.ok(f"  8/8 FINALIZED  agreement={agreement}")

    # -- Step 4 · Transfer ----------------------------------------------------
    log.step("Step 4 · Transfer process")
    url = f"{consumer}/dsp/current/transfers/rpc/setup-request"
    body = _rpc(
        url,
        {
            "associatedAgentPeer": provider_did,
            "providerAddress": provider_dsp,
            "callbackAddress": callback,
            "agreementId": agreement,
            "format": fmt,
        },
    )
    t_pids = {"consumerPid": _dig(body, "response", "consumerPid"), "providerPid": _dig(body, "response", "providerPid")}
    if not all(t_pids.values()):
        raise log.fail(f"Transfer setup-request returned no PIDs\n{json.dumps(body, indent=2)[:1500]}")
    _expect_state(body, url, "REQUESTED")
    log.ok(f"  1/5 REQUESTED  consumerPid={t_pids['consumerPid']} providerPid={t_pids['providerPid']}")

    url = f"{provider}/dsp/current/transfers/rpc/setup-start"
    body = _rpc(url, t_pids)
    _expect_state(body, url, "STARTED")
    dataplane = _find_dataplane_url(body)
    proxy_url = _rewrite_authority(dataplane, provider) if dataplane else None
    log.ok("  2/5 STARTED    (provider)")
    log.info(f"      dataplane: {proxy_url or 'none in the start response'}")

    # -- Step 5 · Data --------------------------------------------------------
    if not data_pull:
        log.info("Skipping the data pull (--no-data-pull)")
    elif not proxy_url:
        raise log.fail("The transfer started but carried no dataplane address to pull from")
    else:
        _check_data(proxy_url, esds, title)

    # -- Step 6 · Lifecycle ---------------------------------------------------
    if suspend:
        log.step("Step 6 · Suspend and resume")
        url = f"{consumer}/dsp/current/transfers/rpc/setup-suspension"
        body = _rpc(url, {**t_pids, "code": "SUSPEND", "reason": ["eunomia e2e suspension"]})
        _expect_state(body, url, "SUSPENDED")
        log.ok("  3/5 SUSPENDED  (consumer)")
        url = f"{consumer}/dsp/current/transfers/rpc/setup-start"
        _expect_state(_rpc(url, t_pids), url, "STARTED")
        log.ok("  4/5 STARTED    (consumer, resumed)")
    else:
        log.info("Skipping the suspend/resume leg (--no-suspend)")

    if keep_open:
        log.step("Transfer left open (--keep-open)")
        if proxy_url:
            log.ok(f"Dataplane proxy URL:\n  {proxy_url}")
        log.info("It stays STARTED until you complete it from the consumer UI. A new run negotiates its own agreement.")
    else:
        url = f"{provider}/dsp/current/transfers/rpc/setup-completion"
        _expect_state(_rpc(url, t_pids), url, "COMPLETED")
        log.ok("  5/5 COMPLETED  (provider)")

    log.step("=" * 60)
    log.ok(
        "END-TO-END TEST PASSED\n"
        f"  Dataset    : {title}\n"
        f"  Agreement  : {agreement}\n"
        f"  Transfer   : {t_pids['consumerPid']} / {t_pids['providerPid']}"
        + (f"\n  Dataplane  : {proxy_url}" if proxy_url else "")
    )
    log.step("=" * 60)
    return 0
