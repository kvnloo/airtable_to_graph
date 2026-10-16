"""Offline CPU-only pre-Bend crossover measurement; synthetic input only.

Measures host-side graph extraction, NOT Airtable I/O, browser layout, or GPU.
"""
import argparse
from pathlib import Path
import statistics
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from graph_core import find_relational_columns, iter_relational_edges


def fixture(n, fields=3, links=2):
    return {"Companies": [
        {"id": f"rec{i:014d}", "fields": {
            f"Relation{j}": [
                f"rec{(i + j + k + 1) % n:014d}" for k in range(links)
            ] for j in range(fields)
        }} for i in range(n)
    ]}


def reference_find(tables):
    # A correct nested-loop reference, not the upstream early-break behavior.
    out = {}
    for name, records in tables.items():
        for record in records:
            for field, value in record["fields"].items():
                if isinstance(value, list) and any(
                    isinstance(i, str) and i.startswith("rec") for i in value
                ):
                    out.setdefault(name, set()).add(field)
    return out


def reference_edges(tables, columns):
    edges = []
    for name, rels in columns.items():
        for col in sorted(rels):
            for rec in tables[name]:
                for target in rec["fields"].get(col, ()):
                    edges.append((rec["id"], target, col))
    return edges


def median_ms(callback, repeats):
    samples = []
    for _ in range(repeats):
        start = perf_counter()
        callback()
        samples.append((perf_counter() - start) * 1000)
    return statistics.median(samples)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=10000)
    p.add_argument("--repeats", type=int, default=7)
    args = p.parse_args()
    if args.rows < 1 or args.repeats < 1:
        p.error("rows and repeats must be >=1")

    tables = fixture(args.rows)
    expected = reference_edges(tables, reference_find(tables))
    actual = list(iter_relational_edges(tables, find_relational_columns(tables)))
    assert sorted(actual) == sorted(expected), "graph edge multiset parity failed"

    baseline = median_ms(
        lambda: reference_edges(tables, reference_find(tables)), args.repeats,
    )
    candidate = median_ms(
        lambda: list(iter_relational_edges(tables, find_relational_columns(tables))),
        args.repeats,
    )
    print(f"rows={args.rows} edges={len(actual)} runs={args.repeats}")
    print(
        f"baseline_ms={baseline:.3f} candidate_ms={candidate:.3f} "
        f"speedup={baseline / candidate:.3f}x"
    )
    print("GPU/Bend: NOT MEASURED by this CPU-only extraction benchmark.")


if __name__ == "__main__":
    main()
