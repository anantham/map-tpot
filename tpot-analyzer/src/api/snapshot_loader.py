"""Snapshot loader for precomputed graph data.

Loads graph structure from Parquet snapshots to avoid rebuilding from SQLite
on every API request. Falls back to live rebuild if snapshot is stale.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import networkx as nx
import pandas as pd

from src.graph import GraphBuildResult

logger = logging.getLogger(__name__)


@dataclass
class SnapshotManifest:
    """Metadata about a graph snapshot."""

    generated_at: datetime
    cache_db_path: str
    cache_db_modified: Optional[datetime]
    node_count: int
    edge_count: int
    include_shadow: bool
    seed_count: int
    resolved_seed_count: int
    metrics_computed: bool
    parameters: dict

    @classmethod
    def from_dict(cls, data: dict) -> SnapshotManifest:
        """Load manifest from dictionary."""
        return cls(
            generated_at=datetime.fromisoformat(data["generated_at"]),
            cache_db_path=data["cache_db_path"],
            cache_db_modified=datetime.fromisoformat(data["cache_db_modified"]) if data.get("cache_db_modified") else None,
            node_count=data["node_count"],
            edge_count=data["edge_count"],
            include_shadow=data["include_shadow"],
            seed_count=data["seed_count"],
            resolved_seed_count=data["resolved_seed_count"],
            metrics_computed=data.get("metrics_computed", False),
            parameters=data.get("parameters", {}),
        )

    def is_stale(self, max_age_seconds: int = 86400) -> bool:
        """Check if snapshot is stale based on age."""
        age = datetime.utcnow() - self.generated_at
        return age.total_seconds() > max_age_seconds

    def cache_updated_since_snapshot(self) -> bool:
        """Check if the cache DB has been modified since snapshot generation."""
        if not self.cache_db_modified:
            return False

        cache_path = Path(self.cache_db_path)
        if not cache_path.exists():
            return False

        cache_mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        return cache_mtime > self.cache_db_modified


class SnapshotLoader:
    """Loads precomputed graph snapshots from disk."""

    def __init__(self, snapshot_dir: Path = Path("data")):
        self.snapshot_dir = Path(snapshot_dir)
        self.nodes_path = self.snapshot_dir / "graph_snapshot.nodes.parquet"
        self.edges_path = self.snapshot_dir / "graph_snapshot.edges.parquet"
        self.manifest_path = self.snapshot_dir / "graph_snapshot.meta.json"

        self._cached_graph: Optional[GraphBuildResult] = None
        self._cached_manifest: Optional[SnapshotManifest] = None

    def snapshot_exists(self) -> bool:
        """Check if all snapshot files exist."""
        return (
            self.nodes_path.exists()
            and self.edges_path.exists()
            and self.manifest_path.exists()
        )

    def load_manifest(self) -> Optional[SnapshotManifest]:
        """Load snapshot manifest."""
        if not self.manifest_path.exists():
            logger.warning(f"Snapshot manifest not found: {self.manifest_path}")
            return None

        try:
            manifest_data = json.loads(self.manifest_path.read_text())
            manifest = SnapshotManifest.from_dict(manifest_data)
            self._cached_manifest = manifest
            return manifest
        except Exception as e:
            logger.exception(f"Failed to load snapshot manifest: {e}")
            return None

    def should_use_snapshot(
        self,
        max_age_seconds: int = 86400,
        check_cache_freshness: bool = True
    ) -> tuple[bool, str]:
        """Determine if snapshot should be used.

        Returns:
            (should_use, reason) tuple
        """
        if not self.snapshot_exists():
            return False, "Snapshot files not found"

        manifest = self.load_manifest()
        if not manifest:
            return False, "Failed to load manifest"

        # Check age
        if manifest.is_stale(max_age_seconds):
            age_hours = (datetime.utcnow() - manifest.generated_at).total_seconds() / 3600
            return False, f"Snapshot is stale ({age_hours:.1f}h old, max {max_age_seconds/3600:.1f}h)"

        # Check if cache has been updated
        if check_cache_freshness and manifest.cache_updated_since_snapshot():
            return False, "Cache DB has been updated since snapshot generation"

        return True, "Snapshot is fresh"

    def load_graph(
        self,
        force_reload: bool = False,
        max_age_seconds: int = 86400
    ) -> Optional[GraphBuildResult]:
        """Load graph from snapshot.

        Args:
            force_reload: Force reload even if cached
            max_age_seconds: Maximum snapshot age before considering stale

        Returns:
            GraphBuildResult or None if snapshot unavailable/stale
        """
        if not force_reload and self._cached_graph:
            logger.debug("Returning cached graph from memory")
            return self._cached_graph

        # Check if we should use snapshot
        should_use, reason = self.should_use_snapshot(max_age_seconds)
        if not should_use:
            logger.warning(f"Not using snapshot: {reason}")
            return None

        try:
            logger.info(f"Loading graph snapshot from {self.snapshot_dir}")

            # Load Parquet files
            nodes_df = pd.read_parquet(self.nodes_path)
            edges_df = pd.read_parquet(self.edges_path)

            logger.info(f"Loaded {len(nodes_df)} nodes and {len(edges_df)} edges from snapshot")

            # Reconstruct NetworkX directed graph
            directed = nx.DiGraph()

            # Add nodes with attributes
            for _, row in nodes_df.iterrows():
                node_attrs = {
                    "username": row.get("username"),
                    "account_display_name": row.get("display_name"),
                    "display_name": row.get("display_name"),
                    "num_followers": row.get("num_followers"),
                    "num_following": row.get("num_following"),
                    "num_likes": row.get("num_likes"),
                    "num_tweets": row.get("num_tweets"),
                    "bio": row.get("bio"),
                    "location": row.get("location"),
                    "website": row.get("website"),
                    "profile_image_url": row.get("profile_image_url"),
                    "provenance": row.get("provenance", "archive"),
                    "shadow": row.get("shadow", False),
                    "fetched_at": row.get("fetched_at"),
                }
                # Filter out None values
                node_attrs = {k: v for k, v in node_attrs.items() if v is not None}
                directed.add_node(row["node_id"], **node_attrs)

            # Add edges with attributes
            for _, row in edges_df.iterrows():
                edge_attrs = {
                    "provenance": row.get("provenance", "archive"),
                    "shadow": row.get("shadow", False),
                    "direction_label": row.get("direction_label"),
                    "fetched_at": row.get("fetched_at"),
                }
                # Parse metadata JSON if present
                if row.get("metadata"):
                    try:
                        edge_attrs["metadata"] = json.loads(row["metadata"])
                    except:
                        pass

                edge_attrs = {k: v for k, v in edge_attrs.items() if v is not None}
                directed.add_edge(row["source"], row["target"], **edge_attrs)

            # Build undirected view (all edges, not just mutual)
            # Note: Snapshot is built with mutual_only=False, so undirected should include all edges
            undirected = nx.Graph()
            undirected.add_nodes_from(directed.nodes(data=True))

            for u, v, data in directed.edges(data=True):
                # Add edge to undirected (sorted to avoid duplicates)
                edge_key = tuple(sorted((u, v)))
                if not undirected.has_edge(*edge_key):
                    weight = data.copy()
                    undirected.add_edge(*edge_key, **weight)

            graph_result = GraphBuildResult(directed=directed, undirected=undirected)

            # Cache in memory
            self._cached_graph = graph_result

            logger.info(f"Snapshot loaded successfully: {directed.number_of_nodes()} nodes, {directed.number_of_edges()} edges")
            return graph_result

        except Exception as e:
            logger.exception(f"Failed to load graph snapshot: {e}")
            return None

    def get_manifest(self) -> Optional[SnapshotManifest]:
        """Get cached manifest."""
        if not self._cached_manifest:
            return self.load_manifest()
        return self._cached_manifest

    def clear_cache(self):
        """Clear in-memory cache."""
        self._cached_graph = None
        self._cached_manifest = None
        logger.info("Snapshot cache cleared")


# Global singleton loader
_snapshot_loader: Optional[SnapshotLoader] = None


def get_snapshot_loader(snapshot_dir: Path = Path("data")) -> SnapshotLoader:
    """Get or create the global snapshot loader."""
    global _snapshot_loader
    if _snapshot_loader is None:
        _snapshot_loader = SnapshotLoader(snapshot_dir)
    return _snapshot_loader
