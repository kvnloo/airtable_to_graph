import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def load_functions():
    source = Path("main.py").read_text()
    tree = ast.parse(source)
    wanted = {"find_relational_columns", "build_knowledge_graph"}
    module = ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted],
        type_ignores=[],
    )
    namespace = {"Network": MagicMock}
    exec(compile(module, "main.py", "exec"), namespace)
    return namespace["find_relational_columns"], namespace["build_knowledge_graph"]


find_relational_columns, build_knowledge_graph = load_functions()


class RelationalColumnsTest(unittest.TestCase):
    def test_finds_every_relationship_on_one_record(self):
        tables = {"Companies": [{"id": "recCompany", "fields": {
            "Name": "Acme", "Founders": ["recFounder"], "Sectors": ["recSector"],
        }}]}
        self.assertEqual(find_relational_columns(tables), {"Companies": {"Founders", "Sectors"}})

    def test_field_order_does_not_change_relationships(self):
        forward = {"Companies": [{"id": "recCompany", "fields": {
            "Founders": ["recFounder"], "Sectors": ["recSector"],
        }}]}
        reverse = {"Companies": [{"id": "recCompany", "fields": {
            "Sectors": ["recSector"], "Founders": ["recFounder"],
        }}]}
        self.assertEqual(find_relational_columns(forward), find_relational_columns(reverse))

    def test_relationships_can_be_discovered_across_records(self):
        tables = {"Companies": [
            {"id": "recA", "fields": {"Founders": ["recFounder"]}},
            {"id": "recB", "fields": {"Sectors": ["recSector"]}},
        ]}
        self.assertEqual(find_relational_columns(tables), {"Companies": {"Founders", "Sectors"}})

    def test_ignores_empty_and_non_record_lists(self):
        tables = {"Companies": [{"id": "recCompany", "fields": {
            "Empty": [], "Tags": ["AI", "Robotics"], "Founders": ["recFounder"],
        }}]}
        self.assertEqual(find_relational_columns(tables), {"Companies": {"Founders"}})

    def test_table_without_relationships_is_omitted(self):
        tables = {"Notes": [{"id": "recNote", "fields": {"Name": "Note", "Tags": ["AI"]}}]}
        self.assertEqual(find_relational_columns(tables), {})

    def test_single_relationship_is_unchanged(self):
        tables = {"Companies": [{"id": "recCompany", "fields": {"Founders": ["recFounder"]}}]}
        self.assertEqual(find_relational_columns(tables), {"Companies": {"Founders"}})

    @patch("builtins.print")
    def test_graph_builder_receives_both_relationships(self, _):
        tables = {
            "Companies": [{"id": "recCompany", "fields": {
                "Name": "Acme", "Founders": ["recFounder"], "Sectors": ["recSector"],
            }}],
            "People": [{"id": "recFounder", "fields": {"Name": "Ada"}}],
            "Sectors": [{"id": "recSector", "fields": {"Name": "AI"}}],
        }
        columns = find_relational_columns(tables)
        network = MagicMock()
        with patch.dict(build_knowledge_graph.__globals__, {"Network": MagicMock(return_value=network)}):
            build_knowledge_graph(tables, columns)
        edges = {(call.args[0], call.args[1], call.kwargs["title"]) for call in network.add_edge.call_args_list}
        self.assertEqual(edges, {
            ("recCompany", "recFounder", "Founders"),
            ("recCompany", "recSector", "Sectors"),
        })


if __name__ == "__main__":
    unittest.main()
