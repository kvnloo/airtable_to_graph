import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def load_functions():
    source = Path("main.py").read_text()
    tree = ast.parse(source)
    wanted = {"get_base_schema", "find_relational_columns", "build_knowledge_graph"}
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
        namespace["build_knowledge_graph"],
        requests,
    )


get_base_schema, find_relational_columns, build_knowledge_graph, requests = load_functions()


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

    def test_field_order_does_not_change_relationships(self):
        forward = {"tables": [{"name": "Companies", "fields": [
            {"name": "Founders", "type": "multipleRecordLinks"},
            {"name": "Sectors", "type": "multipleRecordLinks"},
        ]}]}
        reverse = {"tables": [{"name": "Companies", "fields": [
            {"name": "Sectors", "type": "multipleRecordLinks"},
            {"name": "Founders", "type": "multipleRecordLinks"},
        ]}]}
        self.assertEqual(
            find_relational_columns(forward),
            find_relational_columns(reverse),
        )

    def test_empty_linked_field_is_still_discovered(self):
        schema = {"tables": [{"name": "Companies", "fields": [
            {"name": "Investors", "type": "multipleRecordLinks"},
        ]}]}
        self.assertEqual(
            find_relational_columns(schema),
            {"Companies": {"Investors"}},
        )

    def test_non_link_list_fields_are_ignored_even_if_values_could_look_like_ids(self):
        schema = {"tables": [{"name": "Companies", "fields": [
            {"name": "Tags", "type": "multipleSelects"},
            {"name": "Attachments", "type": "multipleAttachments"},
            {"name": "Founders", "type": "multipleRecordLinks"},
        ]}]}
        self.assertEqual(
            find_relational_columns(schema),
            {"Companies": {"Founders"}},
        )

    def test_tables_without_relationships_are_omitted(self):
        schema = {"tables": [
            {"name": "Notes", "fields": [{"name": "Name", "type": "singleLineText"}]},
            {"name": "Companies", "fields": [{"name": "Founders", "type": "multipleRecordLinks"}]},
        ]}
        self.assertEqual(
            find_relational_columns(schema),
            {"Companies": {"Founders"}},
        )

    def test_missing_tables_is_safe(self):
        self.assertEqual(find_relational_columns({}), {})

    @patch("builtins.print")
    def test_graph_builder_receives_all_schema_relationships(self, _):
        tables = {
            "Companies": [{"id": "recCompany", "fields": {
                "Name": "Acme", "Founders": ["recFounder"], "Sectors": ["recSector"],
            }}],
            "People": [{"id": "recFounder", "fields": {"Name": "Ada"}}],
            "Sectors": [{"id": "recSector", "fields": {"Name": "AI"}}],
        }
        schema = {"tables": [
            {"name": "Companies", "fields": [
                {"name": "Founders", "type": "multipleRecordLinks"},
                {"name": "Sectors", "type": "multipleRecordLinks"},
            ]},
            {"name": "People", "fields": []},
            {"name": "Sectors", "fields": []},
        ]}
        columns = find_relational_columns(schema)
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
