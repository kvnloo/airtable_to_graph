import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def load_functions():
    source = Path("main.py").read_text()
    tree = ast.parse(source)
    wanted = {
        "get_base_schema",
        "find_relational_columns",
        "build_graph_model",
        "build_knowledge_graph",
    }
    module = ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted],
        type_ignores=[],
    )
    requests = MagicMock()
    namespace = {
        "Network": MagicMock,
        "requests": requests,
        "AIRTABLE_API_KEY": "test-token",
        "AIRTABLE_BASE_ID": "appTest",
    }
    exec(compile(module, "main.py", "exec"), namespace)
    return (
        namespace["get_base_schema"],
        namespace["find_relational_columns"],
        namespace["build_graph_model"],
        namespace["build_knowledge_graph"],
        requests,
    )


(
    get_base_schema,
    find_relational_columns,
    build_graph_model,
    build_knowledge_graph,
    requests,
) = load_functions()


class RelationalColumnsTest(unittest.TestCase):
    def setUp(self):
        requests.reset_mock()

    def test_schema_fetch_has_timeout_and_raises_for_http_errors(self):
        response = MagicMock()
        response.json.return_value = {"tables": [{"name": "Companies", "fields": []}]}
        requests.get.return_value = response

        schema = get_base_schema()

        requests.get.assert_called_once_with(
            "https://api.airtable.com/v0/meta/bases/appTest/tables",
            headers={"Authorization": "Bearer test-token"},
            timeout=30,
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(schema["tables"][0]["name"], "Companies")

    def test_finds_every_linked_record_field_from_schema(self):
        schema = {"tables": [{
            "name": "Companies",
            "fields": [
                {"name": "Name", "type": "singleLineText"},
                {"name": "Founders", "type": "multipleRecordLinks"},
                {"name": "Sectors", "type": "multipleRecordLinks"},
            ],
        }]}
        self.assertEqual(
            find_relational_columns(schema),
            {"Companies": {"Founders", "Sectors"}},
        )

    def test_empty_linked_field_is_still_discovered(self):
        schema = {"tables": [{"name": "Companies", "fields": [
            {"name": "Investors", "type": "multipleRecordLinks"},
        ]}]}
        self.assertEqual(
            find_relational_columns(schema),
            {"Companies": {"Investors"}},
        )

    def test_non_link_list_fields_are_ignored(self):
        schema = {"tables": [{"name": "Companies", "fields": [
            {"name": "Tags", "type": "multipleSelects"},
            {"name": "Attachments", "type": "multipleAttachments"},
            {"name": "Founders", "type": "multipleRecordLinks"},
        ]}]}
        self.assertEqual(
            find_relational_columns(schema),
            {"Companies": {"Founders"}},
        )

    def test_graph_model_skips_dangling_links_and_counts_them(self):
        tables = {
            "Companies": [{
                "id": "recCompany",
                "fields": {
                    "Name": "Acme",
                    "Founders": ["recFounder", "recMissing"],
                },
            }],
            "People": [{"id": "recFounder", "fields": {"Name": "Ada"}}],
        }
        nodes, edges, diagnostics = build_graph_model(
            tables,
            {"Companies": {"Founders"}},
        )

        self.assertEqual(set(nodes), {"recCompany", "recFounder"})
        self.assertEqual(edges, [("recCompany", "recFounder", "Founders")])
        self.assertEqual(diagnostics["records"], 2)
        self.assertEqual(diagnostics["edges"], 1)
        self.assertEqual(diagnostics["dangling_edges"], 1)

    def test_graph_model_handles_schema_table_missing_from_records(self):
        nodes, edges, diagnostics = build_graph_model(
            {"Companies": [{"id": "recCompany", "fields": {"Name": "Acme"}}]},
            {"MissingTable": {"Links"}},
        )
        self.assertEqual(set(nodes), {"recCompany"})
        self.assertEqual(edges, [])
        self.assertEqual(diagnostics["relationship_fields"], 1)

    def test_graph_model_counts_invalid_link_values_without_crashing(self):
        tables = {
            "Companies": [{
                "id": "recCompany",
                "fields": {"Name": "Acme", "Founders": "recFounder"},
            }],
        }
        _, edges, diagnostics = build_graph_model(
            tables,
            {"Companies": {"Founders"}},
        )
        self.assertEqual(edges, [])
        self.assertEqual(diagnostics["invalid_link_values"], 1)

    def test_large_synthetic_base_has_exact_linear_accounting(self):
        size = 5000
        people = [
            {"id": f"recPerson{i}", "fields": {"Name": f"Person {i}"}}
            for i in range(size)
        ]
        companies = [
            {
                "id": f"recCompany{i}",
                "fields": {
                    "Name": f"Company {i}",
                    "Founders": [f"recPerson{i}"],
                },
            }
            for i in range(size)
        ]
        nodes, edges, diagnostics = build_graph_model(
            {"Companies": companies, "People": people},
            {"Companies": {"Founders"}},
        )

        self.assertEqual(len(nodes), size * 2)
        self.assertEqual(len(edges), size)
        self.assertEqual(diagnostics, {
            "tables": 2,
            "records": size * 2,
            "nodes": size * 2,
            "edges": size,
            "relationship_fields": 1,
            "dangling_edges": 0,
            "invalid_link_values": 0,
        })

    @patch("builtins.print")
    def test_renderer_receives_only_valid_model_edges(self, _):
        tables = {
            "Companies": [{
                "id": "recCompany",
                "fields": {
                    "Name": "Acme",
                    "Founders": ["recFounder", "recMissing"],
                },
            }],
            "People": [{"id": "recFounder", "fields": {"Name": "Ada"}}],
        }
        network = MagicMock()
        with patch.dict(
            build_knowledge_graph.__globals__,
            {"Network": MagicMock(return_value=network)},
        ):
            returned, diagnostics = build_knowledge_graph(
                tables,
                {"Companies": {"Founders"}},
            )

        self.assertIs(returned, network)
        network.add_edge.assert_called_once_with(
            "recCompany",
            "recFounder",
            title="Founders",
        )
        self.assertEqual(diagnostics["dangling_edges"], 1)


if __name__ == "__main__":
    unittest.main()
