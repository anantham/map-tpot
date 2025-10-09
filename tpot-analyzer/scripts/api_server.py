import sys
import logging
import json
import os
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
LOGGER = logging.getLogger(__name__)

# Add project root to path to allow importing from src
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.config import get_cache_settings
from src.data.shadow_store import get_shadow_store
from sqlalchemy import create_engine

app = Flask(__name__)
# Enable CORS for all routes and origins
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Check for test mode (use TEST_MODE=1 environment variable or --test flag)
TEST_MODE = os.environ.get('TEST_MODE', '0') == '1' or '--test' in sys.argv
TEST_SUBSET_PATH = PROJECT_ROOT / 'data' / 'test_subset.json'

LOGGER.info("Flask app initialized with CORS enabled")
LOGGER.info(f"Test mode: {'ENABLED' if TEST_MODE else 'DISABLED'}")
if TEST_MODE:
    LOGGER.info(f"Using test subset from: {TEST_SUBSET_PATH}")

import networkx as nx
from networkx.algorithms import community

@app.route('/api/graph-data')
def get_graph_data():
    """Endpoint to fetch and return graph data."""
    LOGGER.info("Received request for /api/graph-data")
    try:
        if TEST_MODE:
            # Load from test subset JSON file
            LOGGER.info(f"Loading test subset from {TEST_SUBSET_PATH}")
            with open(TEST_SUBSET_PATH, 'r') as f:
                data = json.load(f)
            accounts = data['accounts']
            edges = data['edges']
            LOGGER.info(f"Loaded {len(accounts)} accounts and {len(edges)} edges from test subset")
        else:
            # Load from database
            settings = get_cache_settings()
            LOGGER.info(f"Using database at: {settings.path}")
            engine = create_engine(f"sqlite:///{settings.path}")
            store = get_shadow_store(engine)

            LOGGER.info("Fetching accounts and edges from database...")
            accounts = store.fetch_accounts()
            edges = store.fetch_edges()
            LOGGER.info(f"Fetched {len(accounts)} accounts and {len(edges)} edges")

        # Process edges to detect mutual relationships
        # Frontend expects: {source: '...', target: '...', mutual: true/false}
        # Backend provides: {source_id: '...', target_id: '...', direction: 'outbound'/'inbound'}
        edge_lookup = {}
        for edge in edges:
            source = edge['source_id']
            target = edge['target_id']
            # Create a canonical key (sorted tuple) to detect bidirectional edges
            key = tuple(sorted([source, target]))

            if key not in edge_lookup:
                edge_lookup[key] = {
                    'source': source,
                    'target': target,
                    'directions': set()
                }
            edge_lookup[key]['directions'].add(edge.get('direction', 'outbound'))

        # Convert to frontend format
        processed_edges = []
        for key, data in edge_lookup.items():
            # An edge is mutual if we have both outbound and inbound directions
            # OR if we have the same edge from both perspectives
            mutual = len(data['directions']) >= 2 or 'bidirectional' in data['directions']

            processed_edges.append({
                'source': data['source'],
                'target': data['target'],
                'mutual': mutual
            })

        # Build NetworkX graph for metrics calculation
        G = nx.Graph()
        for acc in accounts:
            G.add_node(acc['account_id'], **acc)

        for edge in processed_edges:
            G.add_edge(edge['source'], edge['target'])

        pagerank = nx.pagerank(G)
        betweenness = nx.betweenness_centrality(G)
        communities = community.greedy_modularity_communities(G)

        # Convert communities to the format expected by the frontend
        community_mapping = {}
        for i, comm in enumerate(communities):
            for node in comm:
                community_mapping[node] = i

        nodes_for_json = {acc['account_id']: acc for acc in accounts}

        response_data = {
            "graph": {
                "nodes": nodes_for_json,
                "edges": processed_edges,  # Use processed edges with mutual flag
            },
            "metrics": {
                "pagerank": pagerank,
                "betweenness": betweenness,
                "communities": community_mapping,
                "engagement": {},
            },
            "seeds": [], # Placeholder for seeds
            "resolved_seeds": [], # Placeholder for resolved seeds
        }

        LOGGER.info(f"Successfully prepared response with {len(nodes_for_json)} nodes and {len(processed_edges)} edges")
        return jsonify(response_data)

    except Exception as e:
        LOGGER.error(f"Error in get_graph_data: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    PORT = 5001  # Changed from 5000 to avoid conflict with macOS AirPlay
    LOGGER.info("=" * 60)
    LOGGER.info("Starting Graph Explorer API Server")
    LOGGER.info("=" * 60)
    LOGGER.info(f"Server URL: http://localhost:{PORT}")
    LOGGER.info(f"API Endpoint: http://localhost:{PORT}/api/graph-data")
    LOGGER.info("CORS enabled for all origins")
    LOGGER.info("=" * 60)
    app.run(debug=True, port=PORT, host='0.0.0.0')
