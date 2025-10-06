import sys
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

# Add project root to path to allow importing from src
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.config import get_cache_settings
from src.data.shadow_store import get_shadow_store
from sqlalchemy import create_engine

app = Flask(__name__)
CORS(app)

import networkx as nx
from networkx.algorithms import community

@app.route('/api/graph-data')
def get_graph_data():
    """Endpoint to fetch and return graph data."""
    try:
        settings = get_cache_settings()
        engine = create_engine(f"sqlite:///{settings.path}")
        store = get_shadow_store(engine)
        
        accounts = store.fetch_accounts()
        edges = store.fetch_edges()

        G = nx.Graph()
        for acc in accounts:
            G.add_node(acc['account_id'], **acc)

        for edge in edges:
            G.add_edge(edge['source_id'], edge['target_id'])

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
                "edges": edges,
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
        
        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
