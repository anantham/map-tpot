#!/usr/bin/env python3
"""Test the discovery API endpoint."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph import load_seed_candidates


def test_discovery_endpoint():
    """Test the /api/subgraph/discover endpoint."""
    base_url = "http://localhost:5001"

    # Load some default seeds
    default_seeds = sorted(load_seed_candidates())[:5]  # Just use 5 seeds for testing

    print("=" * 60)
    print("TESTING DISCOVERY API")
    print("=" * 60)
    print(f"Using seeds: {default_seeds[:3]}...")
    print()

    # Test 1: Basic discovery with default weights
    print("[1] Testing basic discovery...")
    response = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": default_seeds,
            "limit": 10,
            "debug": True
        }
    )

    if response.status_code == 200:
        data = response.json()

        # Check if this is an error response
        if 'error' in data:
            print(f"✗ API Error: {data['error']}")
        elif 'recommendations' in data:
            print(f"✓ Found {len(data['recommendations'])} recommendations")
            print(f"  Total candidates: {data['meta']['total_candidates']}")
            print(f"  Computation time: {data['meta']['computation_time_ms']}ms")

            if data['recommendations']:
                top = data['recommendations'][0]
                print(f"\n  Top recommendation: @{top['handle']}")
                print(f"    Display name: {top['display_name']}")
                print(f"    Composite score: {top.get('composite_score', 'N/A')}")
                print(f"    Overlap: {top['explanation']['overlap_count']} connections")
                print(f"    Community: {top['explanation'].get('community_name', 'Unknown')}")
        else:
            print(f"✗ Unexpected response format:")
            print(f"  {list(data.keys())}")
    else:
        print(f"✗ Error: {response.status_code}")
        print(f"  {response.text[:500]}")

    print()

    # Test 2: Custom weights favoring neighbor overlap
    print("[2] Testing with custom weights (favor overlap)...")
    response = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": default_seeds,
            "weights": {
                "neighbor_overlap": 0.7,
                "pagerank": 0.1,
                "community": 0.1,
                "path_distance": 0.1
            },
            "limit": 5
        }
    )

    if response.status_code == 200:
        data = response.json()
        if 'error' in data:
            print(f"✗ API Error: {data['error']}")
        elif 'recommendations' in data:
            print(f"✓ Found {len(data['recommendations'])} recommendations")

            if data['recommendations']:
                for i, rec in enumerate(data['recommendations'][:3], 1):
                    print(f"  {i}. @{rec['handle']} (overlap: {rec['explanation']['overlap_count']})")
    else:
        print(f"✗ Error: {response.status_code}")

    print()

    # Test 3: With filters
    print("[3] Testing with filters...")
    response = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": default_seeds,
            "filters": {
                "min_overlap": 2,
                "max_distance": 2,
                "min_followers": 100,
                "max_followers": 10000
            },
            "limit": 5
        }
    )

    if response.status_code == 200:
        data = response.json()
        if 'error' in data:
            print(f"✗ API Error: {data['error']}")
        elif 'recommendations' in data:
            print(f"✓ Found {len(data['recommendations'])} filtered recommendations")
            print(f"  Total after filtering: {data['meta']['total_candidates']}")
    else:
        print(f"✗ Error: {response.status_code}")

    print()

    # Test 4: Pagination
    print("[4] Testing pagination...")
    response1 = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": default_seeds,
            "limit": 5,
            "offset": 0
        }
    )

    response2 = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": default_seeds,
            "limit": 5,
            "offset": 5
        }
    )

    if response1.status_code == 200 and response2.status_code == 200:
        page1 = response1.json()
        page2 = response2.json()

        if 'recommendations' in page1 and 'recommendations' in page2:
            print(f"✓ Page 1: {len(page1['recommendations'])} results")
            print(f"✓ Page 2: {len(page2['recommendations'])} results")
            print(f"  Has more: {page2['meta']['pagination']['has_more']}")
        else:
            print(f"✗ API Error in pagination")
    else:
        print(f"✗ Error in pagination test")

    print()

    # Test 5: Invalid seeds handling
    print("[5] Testing unknown seeds...")
    response = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": ["unknown_user_xyz", "fake_account_123"] + default_seeds[:1],
            "limit": 5
        }
    )

    if response.status_code == 200:
        data = response.json()
        if 'error' in data:
            print(f"✗ API Error: {data['error']}")
        elif 'recommendations' in data or 'meta' in data:
            if 'warnings' in data:
                print(f"✓ Warnings handled: {data['warnings']}")
            print(f"  Valid seeds used: {data.get('meta', {}).get('seed_count', 'unknown')}")
    else:
        print(f"✗ Error: {response.status_code}")

    print()

    # Test 6: Rate limiting headers
    print("[6] Checking rate limit headers...")
    response = requests.post(
        f"{base_url}/api/subgraph/discover",
        json={
            "seeds": default_seeds[:2],
            "limit": 1
        }
    )

    if response.status_code == 200:
        headers = response.headers
        if 'X-RateLimit-Limit' in headers:
            print(f"✓ Rate limit: {headers['X-RateLimit-Limit']} req/min")
            print(f"  Remaining: {headers['X-RateLimit-Remaining']}")
            print(f"  Reset: {headers['X-RateLimit-Reset']}")
        else:
            print("✗ Rate limit headers missing")

    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_discovery_endpoint()