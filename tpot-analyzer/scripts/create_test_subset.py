#!/usr/bin/env python3
"""Create a small test subset of the graph for fast iteration."""

import sys
from pathlib import Path
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.config import get_cache_settings
from src.data.shadow_store import get_shadow_store
from sqlalchemy import create_engine

def create_test_subset(num_nodes=100):
    """Create a test subset with N nodes and their edges."""
    print(f"Creating test subset with {num_nodes} nodes...")

    settings = get_cache_settings()
    engine = create_engine(f"sqlite:///{settings.path}")
    store = get_shadow_store(engine)

    # Fetch all accounts and edges
    print("Fetching all accounts and edges...")
    all_accounts = store.fetch_accounts()
    all_edges = store.fetch_edges()

    print(f"Total accounts: {len(all_accounts)}")
    print(f"Total edges: {len(all_edges)}")

    # Start with seed accounts (Adi's Seeds)
    seed_usernames = [
        "prerationalist", "gptbrooke", "the_wilderless", "nosilverv",
        "qorprate", "vividvoid_", "pli_cachete", "goblinodds",
        "eigenrobot", "pragueyerrr", "exgenesis", "becomingcritter",
        "astridwilde1", "malcolm_ocean", "m_ashcroft", "visakanv",
        "drmacifer", "tasshinfogleman"
    ]

    # Find seed account IDs
    seed_accounts = []
    for acc in all_accounts:
        username = acc.get('username')
        if username and username.lower() in [s.lower() for s in seed_usernames]:
            seed_accounts.append(acc)

    print(f"Found {len(seed_accounts)} seed accounts")

    # Get their account IDs
    selected_ids = {acc['account_id'] for acc in seed_accounts}

    # Add accounts connected to seeds until we reach num_nodes
    edge_lookup = {}
    for edge in all_edges:
        source = edge['source_id']
        target = edge['target_id']

        if source not in edge_lookup:
            edge_lookup[source] = []
        if target not in edge_lookup:
            edge_lookup[target] = []

        edge_lookup[source].append(target)
        edge_lookup[target].append(source)

    # BFS from seeds to get connected nodes
    queue = list(selected_ids)
    visited = set(selected_ids)

    while len(selected_ids) < num_nodes and queue:
        current = queue.pop(0)

        if current in edge_lookup:
            for neighbor in edge_lookup[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    selected_ids.add(neighbor)
                    queue.append(neighbor)

                    if len(selected_ids) >= num_nodes:
                        break

    # Filter accounts to selected IDs
    subset_accounts = [acc for acc in all_accounts if acc['account_id'] in selected_ids]

    # Filter edges to only those between selected nodes
    subset_edges = [
        edge for edge in all_edges
        if edge['source_id'] in selected_ids and edge['target_id'] in selected_ids
    ]

    print(f"\nSubset created:")
    print(f"  Accounts: {len(subset_accounts)}")
    print(f"  Edges: {len(subset_edges)}")

    # Save to JSON file
    output_file = PROJECT_ROOT / 'data' / 'test_subset.json'

    data = {
        'accounts': subset_accounts,
        'edges': subset_edges,
        'seed_usernames': seed_usernames
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\n✓ Test subset saved to: {output_file}")
    print(f"  Size: {output_file.stat().st_size / 1024:.1f} KB")

    return data

if __name__ == '__main__':
    import sys
    num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    create_test_subset(num_nodes)
