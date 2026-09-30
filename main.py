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

# Build knowledge graph
def build_knowledge_graph(tables, relational_columns):
    print("start building knowledge graphs")
    net = Network(height='1000px', width='100%', bgcolor='#222222', font_color='black')
    nodes = {}

    for table_name, records in tables.items():
        for record in records:
            node_id = record['id']
            node_label = record['fields'].get('Name', '')
            nodes[node_id] = (node_label, table_name)

    for node_id, (node_label, table_name) in nodes.items():
        net.add_node(node_id, label=node_label, title=node_label, group=table_name, shape='box')

    for table_name, columns in relational_columns.items():
        for column in columns:
            for record in tables[table_name]:
                if column in record['fields']:
                    for related_id in record['fields'][column]:
                        net.add_edge(record['id'], related_id, title=column)

    return net

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
    net = build_knowledge_graph(tables, relational_columns)

    # Save graph as HTML file
    net.save_graph('static/graph.html')

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
