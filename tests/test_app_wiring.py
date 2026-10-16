import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeNetwork:
    def __init__(self, **kwargs):
        self.nodes = []
        self.edges = []

    def add_node(self, *args, **kwargs):
        self.nodes.append((args, kwargs))

    def add_edge(self, *args, **kwargs):
        self.edges.append((args, kwargs))


class AppWiringTests(unittest.TestCase):
    def test_build_graph_preserves_all_link_columns(self):
        flask = types.ModuleType("flask")

        class FakeFlask:
            def __init__(self, *_):
                pass

            def route(self, *_):
                return lambda fn: fn

        flask.Flask = FakeFlask
        flask.render_template = lambda x: x

        pyairtable = types.ModuleType("pyairtable")
        pyairtable.Table = type("Table", (), {})

        pyvis = types.ModuleType("pyvis")
        pyvis_network = types.ModuleType("pyvis.network")
        pyvis_network.Network = FakeNetwork

        with patch.dict(sys.modules, {
            "flask": flask, "pyairtable": pyairtable,
            "pyvis": pyvis, "pyvis.network": pyvis_network,
        }), patch.dict(os.environ, {"AIRTABLE_API_KEY": "synthetic-not-a-key"}):
            spec = importlib.util.spec_from_file_location(
                "test_main_under_fixture", Path(__file__).resolve().parents[1] / "main.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            data = {"Companies": [{
                "id": "recA",
                "fields": {
                    "Name": "Demo",
                    "Founder": ["recB"],
                    "Investor": ["recC"],
                },
            }]}
            network = module.build_knowledge_graph(
                data, module.find_relational_columns(data),
            )

        self.assertEqual(len(network.nodes), 1)
        self.assertEqual(
            [(args[0], args[1], kwargs["title"]) for args, kwargs in network.edges],
            [("recA", "recB", "Founder"), ("recA", "recC", "Investor")],
        )


if __name__ == "__main__":
    unittest.main()
