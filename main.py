import requests
from flask import Flask, render_template
from pyairtable import Table
from pyvis.network import Network
import os
from concurrent.futures import ThreadPoolExecutor
from graph_core import find_relational_columns, iter_relational_edges

app = Flask(__name__)

# Airtable configuration
AIRTABLE_API_KEY = os.environ['AIRTABLE_API_KEY']
AIRTABLE_BASE_ID = '' # put your airtable base here

# Retrieve data from Airtable
def get_airtable_data(table_name):
    table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, table_name)
    return table.all()


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

    for source_id, target_id, column in iter_relational_edges(tables, relational_columns):
        net.add_edge(source_id, target_id, title=column)

    return net

@app.route('/')
def index():
    # Get all table names from the base schema
    url = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables"
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    response = requests.get(url, headers=headers)
    base_schema = response.json()
    print(base_schema)
    table_names = [table['name'] for table in base_schema['tables']]

    # Retrieve data from Airtable using parallel processing
    with ThreadPoolExecutor() as executor:
        tables = {table_name: data for table_name, data in zip(table_names, executor.map(get_airtable_data, table_names))}

    # Identify relational columns
    relational_columns = find_relational_columns(tables)

    # Build knowledge graph
    net = build_knowledge_graph(tables, relational_columns)

    # Save graph as HTML file
    net.save_graph('static/graph.html')

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
