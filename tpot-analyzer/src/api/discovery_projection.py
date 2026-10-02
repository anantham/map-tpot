"""Filtering and response projection for bounded discovery results."""
from typing import Any, Dict, List
import networkx as nx

COMMUNITY_LABELS = {
    0: "General",
    1: "Tech/Engineering",
    2: "Philosophy",
    3: "Rationalist",
    4: "AI/ML",
    5: "Builder/Indie",
    6: "Politics",
    7: "Art/Creative",
    8: "Science",
    9: "Economics",
    10: "Education",
    11: "Media/Journalism",
    12: "AI Safety",
    # Add more as needed
}


def apply_filters(
    candidates: List[Dict],
    filters: Dict[str, Any],
    seeds: List[str],
    graph: nx.DiGraph = None
) -> List[Dict]:
    """Apply filters to candidate list."""
    filtered = []

    # Auto-cap min_overlap
    min_overlap = min(
        filters.get('min_overlap', 0),
        len(seeds)
    )

    # Get list of accounts the ego node already follows (if exclude_following is enabled)
    following_set = set()
    if filters.get('exclude_following', False) and len(seeds) == 1 and graph:
        # Only apply if we have exactly one seed (ego node)
        ego_node = seeds[0]
        if ego_node in graph:
            following_set = set(graph.successors(ego_node))

    for candidate in candidates:
        # Exclude following filter (only for ego-network mode)
        if following_set and candidate['candidate'] in following_set:
            continue

        # Distance filter
        if 'max_distance' in filters:
            min_dist = candidate['details']['distance']['min_distance']
            if min_dist is None or min_dist > filters['max_distance']:
                continue

        # Overlap filter
        overlap_count = candidate['details']['overlap']['raw_count']
        if overlap_count < min_overlap:
            continue

        # Follower filters
        metadata = candidate.get('metadata', {})
        num_followers = metadata.get('num_followers')

        if num_followers is None:
            # Unknown follower count
            if filters.get('min_followers', 0) > 0:
                continue  # Can't verify minimum
        else:
            if 'min_followers' in filters and num_followers < filters['min_followers']:
                continue
            if 'max_followers' in filters and num_followers > filters['max_followers']:
                continue

        # Community filters
        community_id = candidate['details']['community']['community_id']

        if 'include_communities' in filters:
            if community_id not in filters['include_communities']:
                continue

        if 'exclude_communities' in filters:
            if community_id in filters['exclude_communities']:
                continue

        # Shadow filter
        if 'include_shadow' in filters and not filters['include_shadow']:
            if metadata.get('is_shadow', False):
                continue

        filtered.append(candidate)

    return filtered


def build_recommendation(
    scored_candidate: Dict,
    graph: nx.DiGraph,
    seeds: List[str]
) -> Dict:
    """Build recommendation object from scored candidate."""
    handle = scored_candidate['candidate']
    node_data = graph.nodes[handle]

    account_id = handle
    username = node_data.get('username') or account_id

    # Get metadata
    metadata = {
        'num_followers': node_data.get('num_followers'),
        'num_following': node_data.get('num_following'),
        'follower_following_ratio': None,
        'is_shadow': node_data.get('shadow', False),
        'bio': node_data.get('bio', '')[:200] if node_data.get('bio') else None,
        'location': node_data.get('location')
    }
    metadata['username'] = username

    # Calculate ratio safely
    if metadata['num_followers'] and metadata['num_following'] and metadata['num_following'] > 0:
        metadata['follower_following_ratio'] = round(
            metadata['num_followers'] / metadata['num_following'], 1
        )
    else:
        metadata['follower_following_ratio'] = None

    # Build explanation
    overlap_details = scored_candidate['details']['overlap']
    community_details = scored_candidate['details']['community']
    distance_details = scored_candidate['details']['distance']

    # Find which seeds connect to this candidate
    overlapping_seeds = [
        seed for seed, count in overlap_details['seed_details'].items()
        if count > 0
    ]

    explanation = {
        'overlapping_seeds': overlapping_seeds,
        'overlap_count': overlap_details['raw_count'],
        'community_id': community_details['community_id'],
        'community_name': COMMUNITY_LABELS.get(community_details['community_id']),
        'min_distance': distance_details['min_distance']
    }

    # Find edges to seeds
    edges_to_seeds = []
    for seed in seeds:
        if seed in graph and handle in graph:
            # Check if there's an edge
            has_forward = graph.has_edge(seed, handle)
            has_reverse = graph.has_edge(handle, seed)

            if has_forward or has_reverse:
                edges_to_seeds.append({
                    'seed': seed,
                    'mutual': has_forward and has_reverse
                })

    return {
        'account_id': account_id,
        'handle': account_id,  # Back-compat: internal identifier
        'username': username,
        'display_name': node_data.get('display_name', username),
        'composite_score': scored_candidate['composite_score'],
        'scores': scored_candidate['scores'],
        'explanation': explanation,
        'metadata': metadata,
        'edges_to_seeds': edges_to_seeds
    }
