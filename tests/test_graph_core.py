import unittest

from graph_core import find_relational_columns, iter_relational_edges, _linked_record_ids


class GraphCoreTests(unittest.TestCase):
    def test_all_relation_columns_are_discovered_within_one_record(self):
        tables = {"Companies": [{"id": "recA", "fields": {"Investors": ["recB"], "Founders": ["recC"]}}]}
        self.assertEqual(find_relational_columns(tables), {"Companies": {"Investors", "Founders"}})
        self.assertEqual(
            list(iter_relational_edges(tables, find_relational_columns(tables))),
            [("recA", "recC", "Founders"), ("recA", "recB", "Investors")],
        )

    def test_empty_first_link_then_valid_link_is_detected(self):
        tables = {"Companies": [{"id": "recA", "fields": {"Investors": ["", 123, "recB"]}}]}
        self.assertEqual(find_relational_columns(tables), {"Companies": {"Investors"}})
        self.assertEqual(
            list(iter_relational_edges(tables, {"Companies": {"Investors"}})),
            [("recA", "recB", "Investors")],
        )

    def test_non_link_list_not_a_relationship(self):
        tables = {"Companies": [{"id": "recA", "fields": {"Tags": ["ai", "ml"], "Grades": [1, 2]}}]}
        self.assertEqual(find_relational_columns(tables), {})

    def test_multiple_tables_and_stable_order(self):
        tables = {
            "A": [{"id": "recA", "fields": {"Z": ["recZ"], "B": ["recB"]}}],
            "B": [{"id": "recB", "fields": {"A": ["recA"]}}],
        }
        result = list(iter_relational_edges(tables, find_relational_columns(tables)))
        self.assertEqual(result, [
            ("recA", "recB", "B"), ("recA", "recZ", "Z"), ("recB", "recA", "A"),
        ])

    def test_missing_fields_do_not_crash(self):
        tables = {"A": [
            {"id": "recA"},
            {"id": "recB", "fields": {"Link": ["recA"]}},
        ]}
        self.assertEqual(
            list(iter_relational_edges(tables, find_relational_columns(tables))),
            [("recB", "recA", "Link")],
        )

    def test_empty_and_wrong_types(self):
        self.assertEqual(list(_linked_record_ids(None)), [])
        self.assertEqual(list(_linked_record_ids("recA")), [])
        self.assertEqual(
            list(_linked_record_ids([1, "", None, "rec1", "rec2"])),
            ["rec1", "rec2"],
        )

    def test_streaming_does_not_materialize_edges(self):
        tables = {"A": [
            {"id": f"rec{i}", "fields": {"Peer": [f"rec{(i+1)%10}"]}}
            for i in range(10)
        ]}
        result = iter_relational_edges(tables, {"A": {"Peer"}})
        self.assertTrue(hasattr(result, "__next__"))
        self.assertEqual(len(list(result)), 10)


if __name__ == "__main__":
    unittest.main()
