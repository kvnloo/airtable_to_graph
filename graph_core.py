"""Pure, deterministic extraction of Airtable linked-record relationships.

Preserves credit to Yohei Nakajima (MIT) for the original
yoheinakajima/airtable_to_graph pipeline. No network, renderer, or GPU I/O.
"""


def _linked_record_ids(value):
    """Yield valid Airtable record IDs in order, ignoring unrelated values."""
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, str) and item.startswith("rec"):
            yield item


def find_relational_columns(tables):
    """Find all relationship columns, not only the first in each record."""
    result = {}
    for table_name, records in tables.items():
        columns = set()
        for record in records:
            for field, value in record.get("fields", {}).items():
                if isinstance(value, list) and any(
                    isinstance(item, str) and item.startswith("rec") for item in value
                ):
                    columns.add(field)
        if columns:
            result[table_name] = columns
    return result


def iter_relational_edges(tables, relational_columns):
    """Yield (source, target, field) triples in deterministic order."""
    for table_name, records in tables.items():
        columns = tuple(sorted(relational_columns.get(table_name, ())))
        for record in records:
            fields = record.get("fields", {})
            for column in columns:
                for target in _linked_record_ids(fields.get(column)):
                    yield record["id"], target, column
