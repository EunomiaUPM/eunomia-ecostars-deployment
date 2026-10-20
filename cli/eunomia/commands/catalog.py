"""Provider catalog: the two ECOSTARS use cases and everything hanging off them.

Per use case (environmental, social) it creates the dataset, an HTTP pull and
an HTTP push distribution, three ODRL policies and one connector instance per
distribution. The pull and push connector templates are shared by both.

Payloads live in static/catalog/; the __PLACEHOLDERS__ in them are filled in
here with the ids the provider returns and the ESDS credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .. import http, log
from ..settings import CATALOG_DIR, Esds


@dataclass(frozen=True)
class UseCase:
    key: str
    dataset: str
    pull_distribution: str
    push_distribution: str
    pull_connector: str
    push_connector: str


USE_CASES = (
    UseCase(
        "environmental",
        "01-dataset-environmental.json",
        "03-distribution-pull-environmental.json",
        "04-distribution-push-environmental.json",
        "12-connector-instance-pull-environmental.json",
        "14-connector-instance-push-environmental.json",
    ),
    UseCase(
        "social",
        "02-dataset-social.json",
        "05-distribution-pull-social.json",
        "06-distribution-push-social.json",
        "13-connector-instance-pull-social.json",
        "15-connector-instance-push-social.json",
    ),
)

POLICY_TEMPLATE = "07-policy-template-instantiate.json"
POLICIES = ("08-policy-commercial.json", "09-policy-research-trial.json")
PULL_TEMPLATE = "10-connector-template-pull.json"
PUSH_TEMPLATE = "11-connector-template-push.json"


def _payload(name: str) -> Dict[str, Any]:
    return json.loads((CATALOG_DIR / name).read_text())


class Catalog:
    def __init__(self, provider_url: str) -> None:
        self.api = f"{provider_url}/api/v1"

    def get(self, path: str) -> Any:
        return http.get_json(f"{self.api}{path}")

    def post(self, path: str, body: Dict[str, Any]) -> Any:
        return http.post_json(f"{self.api}{path}", body)

    def datasets(self) -> List[Dict[str, Any]]:
        return self.get("/catalog-agent/datasets") or []

    def distributions(self) -> List[Dict[str, Any]]:
        return self.get("/catalog-agent/distributions") or []

    def instance_for(self, distribution_id: str) -> Optional[Dict[str, Any]]:
        r = http.request("GET", f"{self.api}/connector/instances/distribution/{distribution_id}")
        return r.json() if r.ok and r.body.strip() else None

    def template(self, payload_name: str) -> Dict[str, Any]:
        """Reuse an existing template with the same interaction and auth, or create it.

        Templates get a server-assigned urn as their name, so there is no
        stable key to look them up by; interaction mode plus authentication
        type is what tells the pull and the push template apart.
        """
        payload = _payload(payload_name)
        mode = payload["interaction"]["mode"]
        auth = payload["authentication"]["type"]
        for existing in self.get("/connector/templates") or []:
            if (existing.get("interaction") or {}).get("mode") == mode and (
                existing.get("authentication") or {}
            ).get("type") == auth:
                log.info(f"  {mode.lower()} connector template exists: {existing['name']}")
                return existing
        created = self.post("/connector/templates", payload)
        log.ok(f"  {mode.lower()} connector template created: {created['name']}")
        return created


def _fill_connector(
    payload: Dict[str, Any], template: Dict[str, Any], distribution_id: str, url_param: str, esds: Esds
) -> Dict[str, Any]:
    payload["templateName"] = template["name"]
    payload["templateVersion"] = template["version"]
    payload["distributionId"] = distribution_id
    params = payload["parameters"]
    params[url_param] = params[url_param].replace("__ESDS_API__", esds.api)
    params["TOKEN"] = esds.api_key
    return payload


def _create_use_case(
    cat: Catalog, uc: UseCase, catalog_id: str, data_service_id: str, pull_tpl: Dict, push_tpl: Dict, esds: Esds
) -> None:
    ds = _payload(uc.dataset)
    ds["catalogId"] = catalog_id
    dataset_id = cat.post("/catalog-agent/datasets", ds)["id"]
    log.ok(f"  dataset      {dataset_id}")

    dist_ids = {}
    for kind, name in (("pull", uc.pull_distribution), ("push", uc.push_distribution)):
        dist = _payload(name)
        dist["dcatAccessService"] = data_service_id
        dist["datasetId"] = dataset_id
        dist_ids[kind] = cat.post("/catalog-agent/distributions", dist)["id"]
        log.ok(f"  {kind} dist    {dist_ids[kind]}")

    tpl = _payload(POLICY_TEMPLATE)
    tpl["entityId"] = dataset_id
    cat.post("/catalog-agent/policy-templates/instantiate-odrl-offer", tpl)
    for name in POLICIES:
        policy = _payload(name)
        policy["entityId"] = dataset_id
        cat.post("/catalog-agent/odrl-policies", policy)
    log.ok(f"  policies     {1 + len(POLICIES)}")

    cat.post(
        "/connector/instances",
        _fill_connector(_payload(uc.pull_connector), pull_tpl, dist_ids["pull"], "ACCESS_URL", esds),
    )
    cat.post(
        "/connector/instances",
        _fill_connector(_payload(uc.push_connector), push_tpl, dist_ids["push"], "SUB_URL", esds),
    )
    log.ok("  connectors   pull + push")


def populate(provider_url: str, esds: Esds, force: bool = False) -> None:
    """Create whatever use case is missing. With force, create them all again."""
    cat = Catalog(provider_url)
    log.step(f"Populating the provider catalog (ESDS: {esds.api})")

    catalog_id = cat.get("/catalog-agent/catalogs/main")["id"]
    data_service_id = cat.get("/catalog-agent/data-services/main")["id"]
    existing = {d.get("dctTitle"): d for d in cat.datasets()}

    pending = []
    for uc in USE_CASES:
        title = _payload(uc.dataset)["dctTitle"]
        if title in existing and not force:
            log.info(f"{uc.key}: already in the catalog, skipping ({existing[title]['id']})")
        else:
            pending.append(uc)
    if not pending:
        log.ok("Catalog already populated")
        return

    pull_tpl = cat.template(PULL_TEMPLATE)
    push_tpl = cat.template(PUSH_TEMPLATE)
    for uc in pending:
        log.step(f"Creating the {uc.key} use case")
        _create_use_case(cat, uc, catalog_id, data_service_id, pull_tpl, push_tpl, esds)
    log.ok("\nCatalog populated")


def show(provider_url: str) -> None:
    """Print each dataset with its distributions and their connector instances."""
    cat = Catalog(provider_url)
    datasets = cat.datasets()
    if not datasets:
        log.info("The provider catalog is empty. Run: eunomia catalog populate")
        return
    by_dataset: Dict[str, List[Dict[str, Any]]] = {}
    for dist in cat.distributions():
        by_dataset.setdefault(dist.get("datasetId") or "", []).append(dist)
    for ds in datasets:
        print(f"{ds['id']}  {ds.get('dctTitle')}")
        for dist in by_dataset.get(ds["id"], []):
            inst = cat.instance_for(dist["id"])
            conn = inst["id"] if inst else "no connector instance"
            fmt = dist.get("dctFormat") or dist.get("dctFormats") or "?"
            print(f"    {fmt:<10} {dist['id']}  -> {conn}")
