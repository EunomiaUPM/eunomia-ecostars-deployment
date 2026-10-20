"""Unit tests for the parts that need no running stack.

    python3 -m unittest discover -s cli/tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eunomia import settings  # noqa: E402
from eunomia.cli import build_parser  # noqa: E402
from eunomia.commands import catalog, images, restart, stack  # noqa: E402


class ParseDotenv(unittest.TestCase):
    def test_comments_quotes_and_hashes(self):
        env = settings.parse_dotenv(
            "# comment\n"
            "\n"
            "A=1\n"
            "B = spaced \n"
            "C=\"quoted # kept\"\n"
            "D='single'\n"
            "E=value # inline comment\n"
            "F=pa#ss\n"
            "export G=exported\n"
            "not a pair\n"
        )
        self.assertEqual(
            env,
            {"A": "1", "B": "spaced", "C": "quoted # kept", "D": "single", "E": "value", "F": "pa#ss", "G": "exported"},
        )


class ResolveNodes(unittest.TestCase):
    def test_default_is_the_dataspace(self):
        self.assertEqual(stack.resolve_nodes([]), ["authority", "provider", "consumer"])

    def test_all_adds_the_client(self):
        self.assertEqual(stack.resolve_nodes(["all"]), ["authority", "provider", "consumer", "client"])

    def test_dependency_order_wins_over_typed_order(self):
        self.assertEqual(stack.resolve_nodes(["consumer", "authority"]), ["authority", "consumer"])


class ImageRefs(unittest.TestCase):
    def test_split(self):
        self.assertEqual(images._split("quay.io/eunomia_upm/ds-agent:v0.4.0"), ("quay.io", "eunomia_upm/ds-agent", "v0.4.0"))
        self.assertEqual(images._split("rmenendez8/fafnir:v0.2.0"), ("docker.io", "rmenendez8/fafnir", "v0.2.0"))
        self.assertEqual(images._split("postgres:18"), ("docker.io", "library/postgres", "18"))
        self.assertEqual(images._split("postgres"), ("docker.io", "library/postgres", ""))

    def test_every_standalone_image_is_pinned(self):
        for ref in images.pinned("standalone"):
            if ref.startswith("metabase/"):
                continue  # client stack, owned by the ecostars-consumer-case submodule
            self.assertTrue(images._split(ref)[2], f"{ref} has no tag")
            self.assertNotIn(":latest", ref)


class Catalog(unittest.TestCase):
    def test_payloads_exist(self):
        names = {catalog.POLICY_TEMPLATE, catalog.PULL_TEMPLATE, catalog.PUSH_TEMPLATE, *catalog.POLICIES}
        for uc in catalog.USE_CASES:
            names |= {uc.dataset, uc.pull_distribution, uc.push_distribution, uc.pull_connector, uc.push_connector}
        for name in names:
            self.assertTrue((settings.CATALOG_DIR / name).is_file(), name)

    def test_fill_connector(self):
        esds = settings.Esds("https://esds.example/esds", "secret")
        payload = catalog._payload("12-connector-instance-pull-environmental.json")
        filled = catalog._fill_connector(payload, {"name": "urn:t", "version": "1.0"}, "urn:d", "ACCESS_URL", esds)
        self.assertEqual(filled["templateName"], "urn:t")
        self.assertEqual(filled["distributionId"], "urn:d")
        self.assertEqual(filled["parameters"]["ACCESS_URL"], "https://esds.example/esds/environmental")
        self.assertEqual(filled["parameters"]["TOKEN"], "secret")


class Compose(unittest.TestCase):
    def test_every_compose_file_exists(self):
        for env in settings.ENVIRONMENTS:
            for node, s in settings.stacks(env).items():
                self.assertTrue(s.compose.is_file(), f"{env}/{node}: {s.compose}")


class Restart(unittest.TestCase):
    def test_agent_restart_keeps_the_database(self):
        script = restart._remote_script("provider", "/srv/x", "docker-compose.provider.yaml", "provider", "provider-fafnir-wallet")
        self.assertIn("--no-deps provider-fafnir-wallet provider", script)
        self.assertNotIn("down", script)


class Parser(unittest.TestCase):
    def test_up_without_nodes(self):
        args = build_parser().parse_args(["up"])
        self.assertEqual((args.nodes, args.env), ([], "standalone"))

    def test_onboard_register_node(self):
        args = build_parser().parse_args(["onboard", "register", "provider"])
        self.assertEqual((args.step, args.node), ("register", "provider"))


if __name__ == "__main__":
    unittest.main()
