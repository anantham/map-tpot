#!/usr/bin/env python3
"""Quick test script to verify the API is working."""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

import requests
import json

def test_api():
    """Test the graph data API endpoint."""
    url = "http://localhost:5001/api/graph-data"

    print(f"Testing API endpoint: {url}")
    print("=" * 60)

    try:
        response = requests.get(url, timeout=10)

        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print()

        if response.status_code == 200:
            data = response.json()
            print("✅ SUCCESS!")
            print()
            print(f"Nodes: {len(data.get('graph', {}).get('nodes', {}))}")
            print(f"Edges: {len(data.get('graph', {}).get('edges', []))}")
            print(f"Seeds: {data.get('seeds', [])}")
            print(f"Metrics available: {list(data.get('metrics', {}).keys())}")

            # Show sample edge
            edges = data.get('graph', {}).get('edges', [])
            if edges:
                print()
                print("Sample edge:")
                print(json.dumps(edges[0], indent=2))
        else:
            print(f"❌ ERROR: {response.status_code}")
            print(response.text)

    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to the server")
        print("Make sure the API server is running:")
        print("  .venv/bin/python3 scripts/api_server.py")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == '__main__':
    test_api()
