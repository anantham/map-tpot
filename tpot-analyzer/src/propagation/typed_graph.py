"""Typed multi-relational graph for community propagation.

Each edge type (follow, reply, like, RT, co-followed) is stored as a
separate sparse matrix. This preserves the semantic meaning of each
relationship type while allowing flexible combination for different
purposes:

- Propagation: combine with configurable weights per edge type
- Analysis: query specific relationship types (reciprocity, engagement)
- NMF: use different subsets of edge types for different runs
- Confidence: weight edge types differently per community

Edge types and their semantics:
  follow      — "I want to hear what you say" (persistent, architectural)
  reply       — "I'm engaging with this specific thing" (episodic, conversational)
  like        — "I endorse this" (low-effort, reflexive)
  rt          — "My audience should see this" (amplification, deliberate)
  cofollowed  — "We share an audience" (structural, neither party acted)
  quote       — "I'm commenting on your exact words" (high-effort, semantic-rich)
  mention     — "I'm referencing you" (directed, potentially noisy)
  follower    — "They follow me" (inbound, enables reciprocity detection)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
import scipy.sparse as sp


# Default weights for combining edge types into a single adjacency.
# These can be overridden per propagation run or per community.
DEFAULT_EDGE_WEIGHTS = {
    "follow": 1.0,
    "reply": 0.5,
    "like": 0.3,
    "rt": 0.6,
    "cofollowed": 0.1,
    "quote": 0.7,
    "mention": 0.15,
    "follower": 0.0,  # not combined by default — used for reciprocity queries
}


class TypedGraph:
    """Multi-relational graph with separate adjacency matrices per edge type.

    Usage:
        graph = TypedGraph.from_archive(db_path)
        adj = graph.combine()                    # single matrix for propagation
        adj = graph.combine({"follow": 1, "reply": 0.8})  # custom weights
        follow_mat = graph.get("follow")         # single edge type
        graph.edge_summary()                     # print stats
    """

    EDGE_TYPES = ("follow", "reply", "like", "rt", "cofollowed", "quote", "mention", "follower")

    def __init__(self, node_ids: list[str]):
        self.node_ids = node_ids
        self.node_idx = {nid: i for i, nid in enumerate(node_ids)}
        self.n = len(node_ids)
        self._matrices: dict[str, sp.csr_matrix] = {}

    def set(self, edge_type: str, matrix: sp.csr_matrix) -> None:
        """Store a sparse matrix for an edge type."""
        assert matrix.shape == (self.n, self.n), (
            f"Matrix shape {matrix.shape} doesn't match node count {self.n}"
        )
        self._matrices[edge_type] = matrix

    def get(self, edge_type: str) -> Optional[sp.csr_matrix]:
        """Get the sparse matrix for an edge type, or None."""
        return self._matrices.get(edge_type)

    def has(self, edge_type: str) -> bool:
        return edge_type in self._matrices

    def combine(
        self,
        weights: Optional[dict[str, float]] = None,
    ) -> sp.csr_matrix:
        """Combine all edge types into a single weighted adjacency matrix.

        Args:
            weights: per-type weights. Missing types default to 0.
                     If None, uses DEFAULT_EDGE_WEIGHTS.
        """
        if weights is None:
            weights = DEFAULT_EDGE_WEIGHTS

        combined = sp.csr_matrix((self.n, self.n), dtype=np.float32)
        for edge_type, mat in self._matrices.items():
            w = weights.get(edge_type, 0.0)
            if w > 0:
                combined = combined + mat.astype(np.float32) * w

        return combined

    def edge_summary(self) -> dict[str, int]:
        """Return {edge_type: nnz} for all stored matrices."""
        return {
            etype: mat.nnz
            for etype, mat in self._matrices.items()
        }

    def print_summary(self) -> None:
        """Print a human-readable summary."""
        print(f"  TypedGraph: {self.n:,} nodes")
        total = 0
        for etype in self.EDGE_TYPES:
            mat = self._matrices.get(etype)
            if mat is not None:
                print(f"    {etype:12s}: {mat.nnz:>10,} edges")
                total += mat.nnz
            else:
                print(f"    {etype:12s}: not loaded")
        print(f"    {'TOTAL':12s}: {total:>10,} edges")

    def neighbors(
        self, account_id: str, edge_type: Optional[str] = None,
    ) -> list[tuple[str, float]]:
        """Get neighbors of an account, optionally filtered by edge type.

        Returns list of (neighbor_id, weight) sorted by weight descending.
        """
        idx = self.node_idx.get(account_id)
        if idx is None:
            return []

        if edge_type:
            mat = self._matrices.get(edge_type)
            if mat is None:
                return []
            row = mat[idx].toarray().flatten()
        else:
            combined = self.combine()
            row = combined[idx].toarray().flatten()

        nonzero = np.nonzero(row)[0]
        results = [(self.node_ids[j], float(row[j])) for j in nonzero]
        results.sort(key=lambda x: -x[1])
        return results

    def typed_degree(self, account_id: str) -> dict[str, int]:
        """Get per-type degree (neighbor count) for an account."""
        idx = self.node_idx.get(account_id)
        if idx is None:
            return {}
        return {
            etype: int(mat[idx].nnz)
            for etype, mat in self._matrices.items()
        }

    def reciprocity(self, account_id: str) -> Optional[float]:
        """Compute reciprocity ratio: mutual_follows / inbound_follows.

        Requires both 'follow' and 'follower' matrices.
        Returns None if either is missing or the account has no inbound followers.

        Famous accounts have low reciprocity (< 0.06).
        TPOT members have high reciprocity (> 0.17).
        See EXP-003 in docs/EXPERIMENT_LOG.md.
        """
        follow_mat = self._matrices.get("follow")
        follower_mat = self._matrices.get("follower")
        if follow_mat is None or follower_mat is None:
            return None

        idx = self.node_idx.get(account_id)
        if idx is None:
            return None

        # outbound: who this account follows (row in follow matrix)
        outbound = set(follow_mat[idx].indices)
        # inbound: who follows this account
        # follower matrix is stored as follower→account (row→col),
        # so column idx gives inbound followers. CSC is needed for correct column indexing.
        inbound = set(follower_mat.tocsc()[:, idx].indices)

        if not inbound:
            return None

        mutuals = len(outbound & inbound)
        return mutuals / len(inbound)

    @classmethod
    def from_archive(
        cls,
        db_path: Path,
        load_types: Optional[set[str]] = None,
    ) -> "TypedGraph":
        """Build a TypedGraph from archive_tweets.db.

        Args:
            db_path: Path to archive_tweets.db.
            load_types: Which edge types to load. None = all available.
        """
        if load_types is None:
            load_types = set(cls.EDGE_TYPES)

        conn = sqlite3.connect(str(db_path))

        # 1. Discover all node IDs from follow graph
        print("  Loading node IDs from account_following...")
        sources = set(
            r[0] for r in conn.execute(
                "SELECT DISTINCT account_id FROM account_following"
            ).fetchall()
        )
        targets = set(
            r[0] for r in conn.execute(
                "SELECT DISTINCT following_account_id FROM account_following"
            ).fetchall()
        )
        all_nodes = sorted(sources | targets)
        graph = cls(all_nodes)
        print(f"  Nodes: {graph.n:,} ({len(sources):,} sources, {len(targets):,} targets)")

        # 2. Follow edges
        if "follow" in load_types:
            print("  Loading follow edges...")
            follows = conn.execute(
                "SELECT account_id, following_account_id FROM account_following"
            ).fetchall()
            rows, cols, vals = [], [], []
            for src, tgt in follows:
                i = graph.node_idx.get(src)
                j = graph.node_idx.get(tgt)
                if i is not None and j is not None:
                    rows.append(i)
                    cols.append(j)
                    vals.append(1.0)
            mat = sp.csr_matrix(
                (np.array(vals, dtype=np.float32), (rows, cols)),
                shape=(graph.n, graph.n),
            )
            graph.set("follow", mat)
            print(f"    {mat.nnz:,} follow edges")

        # 3. Reply edges (from signed_reply)
        if "reply" in load_types:
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='signed_reply'"
                ).fetchone()[0]
                if exists:
                    print("  Loading signed reply edges...")
                    reply_data = conn.execute(
                        "SELECT replier_id, author_id, reply_count, heuristic FROM signed_reply"
                    ).fetchall()
                    rows, cols, vals = [], [], []
                    for replier, author, count, heuristic in reply_data:
                        i = graph.node_idx.get(replier)
                        j = graph.node_idx.get(author)
                        if i is not None and j is not None:
                            w = min(count / 5.0, 1.0)
                            if heuristic == "author_liked":
                                w *= 1.5
                            rows.append(i)
                            cols.append(j)
                            vals.append(w)
                    if vals:
                        mat = sp.csr_matrix(
                            (np.array(vals, dtype=np.float32), (rows, cols)),
                            shape=(graph.n, graph.n),
                        )
                        graph.set("reply", mat)
                        print(f"    {mat.nnz:,} reply edges")
            except Exception as e:
                print(f"    Warning: reply loading failed: {e}")

        # 4. Like and RT edges (from account_engagement_agg)
        if "like" in load_types or "rt" in load_types:
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='account_engagement_agg'"
                ).fetchone()[0]
                if exists:
                    print("  Loading engagement edges (like + RT)...")
                    eng_data = conn.execute(
                        "SELECT source_id, target_id, like_count, rt_count "
                        "FROM account_engagement_agg"
                    ).fetchall()

                    if "like" in load_types:
                        like_rows, like_cols, like_vals = [], [], []
                        for src, tgt, likes, rts in eng_data:
                            if likes and likes > 0:
                                i = graph.node_idx.get(src)
                                j = graph.node_idx.get(tgt)
                                if i is not None and j is not None:
                                    like_rows.append(i)
                                    like_cols.append(j)
                                    like_vals.append(min(likes / 50.0, 1.0))
                        if like_vals:
                            mat = sp.csr_matrix(
                                (np.array(like_vals, dtype=np.float32),
                                 (like_rows, like_cols)),
                                shape=(graph.n, graph.n),
                            )
                            graph.set("like", mat)
                            print(f"    {mat.nnz:,} like edges")

                    if "rt" in load_types:
                        rt_rows, rt_cols, rt_vals = [], [], []
                        for src, tgt, likes, rts in eng_data:
                            if rts and rts > 0:
                                i = graph.node_idx.get(src)
                                j = graph.node_idx.get(tgt)
                                if i is not None and j is not None:
                                    rt_rows.append(i)
                                    rt_cols.append(j)
                                    rt_vals.append(min(rts / 10.0, 1.0))
                        if rt_vals:
                            mat = sp.csr_matrix(
                                (np.array(rt_vals, dtype=np.float32),
                                 (rt_rows, rt_cols)),
                                shape=(graph.n, graph.n),
                            )
                            graph.set("rt", mat)
                            print(f"    {mat.nnz:,} RT edges")
            except Exception as e:
                print(f"    Warning: engagement loading failed: {e}")

        # 5. Co-followed similarity (undirected)
        if "cofollowed" in load_types:
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cofollowed_similarity'"
                ).fetchone()[0]
                if exists:
                    cofollowed_cols = {
                        r[1] for r in conn.execute(
                            "PRAGMA table_info(cofollowed_similarity)"
                        ).fetchall()
                    }
                    if "account_id_1" in cofollowed_cols:
                        id1_col, id2_col = "account_id_1", "account_id_2"
                    elif "account_a" in cofollowed_cols:
                        id1_col, id2_col = "account_a", "account_b"
                    elif "source_id" in cofollowed_cols:
                        id1_col, id2_col = "source_id", "target_id"
                    else:
                        raise ValueError(f"Unknown columns: {cofollowed_cols}")

                    shared_col = (
                        "shared_followers" if "shared_followers" in cofollowed_cols
                        else "jaccard" if "jaccard" in cofollowed_cols
                        else "similarity"
                    )

                    print("  Loading co-followed similarity edges...")
                    cf_data = conn.execute(
                        f"SELECT {id1_col}, {id2_col}, {shared_col} "
                        "FROM cofollowed_similarity"
                    ).fetchall()
                    rows, cols, vals = [], [], []
                    for id1, id2, shared in cf_data:
                        i = graph.node_idx.get(id1)
                        j = graph.node_idx.get(id2)
                        if i is not None and j is not None:
                            w = min(shared / 20.0, 1.0)
                            # Undirected
                            rows.extend([i, j])
                            cols.extend([j, i])
                            vals.extend([w, w])
                    if vals:
                        mat = sp.csr_matrix(
                            (np.array(vals, dtype=np.float32), (rows, cols)),
                            shape=(graph.n, graph.n),
                        )
                        graph.set("cofollowed", mat)
                        print(f"    {mat.nnz:,} co-followed edges (undirected)")
            except Exception as e:
                print(f"    Warning: co-followed loading failed: {e}")

        # 6. Quote edges (from quote_graph)
        if "quote" in load_types:
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quote_graph'"
                ).fetchone()[0]
                if exists:
                    print("  Loading quote edges...")
                    quote_data = conn.execute(
                        "SELECT source_id, target_id, quote_count FROM quote_graph"
                    ).fetchall()
                    rows, cols, vals = [], [], []
                    for src, tgt, count in quote_data:
                        i = graph.node_idx.get(src)
                        j = graph.node_idx.get(tgt)
                        if i is not None and j is not None:
                            rows.append(i)
                            cols.append(j)
                            vals.append(min(count / 5.0, 1.0))
                    if vals:
                        mat = sp.csr_matrix(
                            (np.array(vals, dtype=np.float32), (rows, cols)),
                            shape=(graph.n, graph.n),
                        )
                        graph.set("quote", mat)
                        print(f"    {mat.nnz:,} quote edges")
            except Exception as e:
                print(f"    Warning: quote loading failed: {e}")

        # 7. Mention edges (from mention_graph)
        if "mention" in load_types:
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='mention_graph'"
                ).fetchone()[0]
                if exists:
                    print("  Loading mention edges...")
                    mention_data = conn.execute(
                        "SELECT source_id, target_id, mention_count FROM mention_graph"
                    ).fetchall()
                    rows, cols, vals = [], [], []
                    for src, tgt, count in mention_data:
                        i = graph.node_idx.get(src)
                        j = graph.node_idx.get(tgt)
                        if i is not None and j is not None:
                            rows.append(i)
                            cols.append(j)
                            vals.append(min(count / 10.0, 1.0))
                    if vals:
                        mat = sp.csr_matrix(
                            (np.array(vals, dtype=np.float32), (rows, cols)),
                            shape=(graph.n, graph.n),
                        )
                        graph.set("mention", mat)
                        print(f"    {mat.nnz:,} mention edges")
            except Exception as e:
                print(f"    Warning: mention loading failed: {e}")

        # 8. Follower edges (from account_followers — inbound follows)
        if "follower" in load_types:
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='account_followers'"
                ).fetchone()[0]
                if exists:
                    print("  Loading follower edges (inbound)...")
                    follower_data = conn.execute(
                        "SELECT account_id, follower_account_id FROM account_followers"
                    ).fetchall()
                    rows, cols, vals = [], [], []
                    for account, follower in follower_data:
                        i = graph.node_idx.get(follower)
                        j = graph.node_idx.get(account)
                        if i is not None and j is not None:
                            rows.append(i)
                            cols.append(j)
                            vals.append(1.0)
                    if vals:
                        mat = sp.csr_matrix(
                            (np.array(vals, dtype=np.float32), (rows, cols)),
                            shape=(graph.n, graph.n),
                        )
                        graph.set("follower", mat)
                        print(f"    {mat.nnz:,} follower edges (inbound)")
            except Exception as e:
                print(f"    Warning: follower loading failed: {e}")

        conn.close()
        graph.print_summary()
        return graph
