import requests
from flask import Flask, render_template
from pyairtable import Table
from pyvis.network import Network
import os
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# Airtable configuration
AIRTABLE_API_KEY = os.environ['AIRTABLE_API_KEY']
AIRTABLE_BASE_ID = '' # put your airtable base here

# Retrieve data from Airtable
def get_airtable_data(table_name):
    table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, table_name)
    return table.all()

def get_base_schema():
    url = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables"
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

# Identify relational columns from Airtable's schema instead of guessing
# from record values. Linked-record fields are typed as multipleRecordLinks.
def find_relational_columns(base_schema):
    print("finding relational columns")
    relational_columns = {}
    for table in base_schema.get('tables', []):
        columns = {
            field['name']
            for field in table.get('fields', [])
            if field.get('type') == 'multipleRecordLinks'
        }
        if columns:
            relational_columns[table['name']] = columns
    return relational_columns

def build_graph_model(tables, relational_columns):
    """Build a render-ready graph model and bounded scale diagnostics."""
    nodes = {}
    record_count = 0

    for table_name, records in tables.items():
        record_count += len(records)
        for record in records:
            node_id = record['id']
            node_label = record.get('fields', {}).get('Name', '')
            nodes[node_id] = (node_label, table_name)

    edges = []
    dangling_edges = 0
    invalid_link_values = 0

    for table_name, columns in relational_columns.items():
        for record in tables.get(table_name, []):
            fields = record.get('fields', {})
            for column in columns:
                if column not in fields:
                    continue
                related_ids = fields[column]
                if not isinstance(related_ids, list):
                    invalid_link_values += 1
                    continue
                for related_id in related_ids:
                    if related_id not in nodes:
                        dangling_edges += 1
                        continue
                    edges.append((record['id'], related_id, column))

    diagnostics = {
        'tables': len(tables),
        'records': record_count,
        'nodes': len(nodes),
        'edges': len(edges),
        'relationship_fields': sum(len(columns) for columns in relational_columns.values()),
        'dangling_edges': dangling_edges,
        'invalid_link_values': invalid_link_values,
    }
    return nodes, edges, diagnostics

# Build knowledge graph
def build_knowledge_graph(tables, relational_columns):
    print("start building knowledge graphs")
    net = Network(height='1000px', width='100%', bgcolor='#222222', font_color='black')
    nodes, edges, diagnostics = build_graph_model(tables, relational_columns)

    for node_id, (node_label, table_name) in nodes.items():
        net.add_node(node_id, label=node_label, title=node_label, group=table_name, shape='box')

    for source_id, related_id, column in edges:
        net.add_edge(source_id, related_id, title=column)

    return net, diagnostics

@app.route('/')
def index():
    # Get the base schema once. It supplies both table names and the
    # authoritative linked-record field types.
    base_schema = get_base_schema()
    table_names = [table['name'] for table in base_schema['tables']]

    # Retrieve data from Airtable using parallel processing
    with ThreadPoolExecutor() as executor:
        tables = {table_name: data for table_name, data in zip(table_names, executor.map(get_airtable_data, table_names))}

    # Identify relational columns from schema metadata.
    relational_columns = find_relational_columns(base_schema)

    # Build knowledge graph
    net, diagnostics = build_knowledge_graph(tables, relational_columns)
    print(
        "graph diagnostics: "
        f"{diagnostics['records']} records, "
        f"{diagnostics['edges']} edges, "
        f"{diagnostics['dangling_edges']} dangling links"
    )

    # Save graph as HTML file
    net.save_graph('static/graph.html')

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
