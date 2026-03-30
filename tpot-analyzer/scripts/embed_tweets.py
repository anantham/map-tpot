"""Embed tweets using LM Studio's local embedding model.

Multi-scale clustering experiment: embed authored tweets into a shared
semantic space, then cluster at k=2,4,8,16,32,64,128,256 to discover
latent structure at multiple scales.

Designed to run on the GPU machine (asus-strix-scar) with LM Studio
serving an embedding model on localhost:1234.

Usage:
    # Embed all authored tweets (5.5M, ~hours)
    python scripts/embed_tweets.py --db data/archive_tweets.db

    # Embed a sample first (for testing)
    python scripts/embed_tweets.py --db data/archive_tweets.db --sample 10000

    # Resume from where we left off
    python scripts/embed_tweets.py --db data/archive_tweets.db --resume

    # Just cluster (embeddings already computed)
    python scripts/embed_tweets.py --db data/archive_tweets.db --cluster-only
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import struct
import sys
import time
from pathlib import Path

import numpy as np
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
LMSTUDIO_URL = "http://localhost:1234/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-qwen3-embedding-0.6b"
BATCH_SIZE = 256  # tweets per API call — benchmarked at 46/sec on RTX 3080
CHECKPOINT_EVERY = 5000  # save progress every N tweets
MAX_TWEET_CHARS = 512  # truncate longer tweets


# ── Schema ──────────────────────────────────────────────────────────────

def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create tables for storing embeddings and cluster assignments."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tweet_embedding (
            tweet_id TEXT PRIMARY KEY,
            embedding BLOB NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tweet_cluster (
            tweet_id TEXT NOT NULL,
            k INTEGER NOT NULL,
            cluster_id INTEGER NOT NULL,
            distance REAL,
            PRIMARY KEY (tweet_id, k)
        );

        CREATE TABLE IF NOT EXISTS cluster_run (
            k INTEGER PRIMARY KEY,
            inertia REAL,
            n_tweets INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()


# ── Embedding ───────────────────────────────────────────────────────────

def get_embedding_dim() -> int:
    """Query the model for its embedding dimension."""
    resp = requests.post(
        LMSTUDIO_URL,
        json={"model": EMBEDDING_MODEL, "input": ["test"]},
        timeout=30,
    )
    resp.raise_for_status()
    return len(resp.json()["data"][0]["embedding"])


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via LM Studio."""
    resp = requests.post(
        LMSTUDIO_URL,
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    # LM Studio returns embeddings in order of input
    return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]


def embedding_to_blob(emb: list[float]) -> bytes:
    """Pack a float list into a compact binary blob."""
    return struct.pack(f"{len(emb)}f", *emb)


def blob_to_embedding(blob: bytes, dim: int) -> np.ndarray:
    """Unpack a binary blob into a numpy array."""
    return np.array(struct.unpack(f"{dim}f", blob), dtype=np.float32)


def get_already_embedded(conn: sqlite3.Connection) -> set[str]:
    """Get set of tweet_ids that already have embeddings."""
    rows = conn.execute("SELECT tweet_id FROM tweet_embedding").fetchall()
    return {r[0] for r in rows}


def load_tweets_from_csv(csv_path: Path) -> list[tuple[str, str, str]]:
    """Load tweets from CSV (tweet_id, account_id, full_text)."""
    import csv
    tweets = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("full_text"):
                tweets.append((row["tweet_id"], row["account_id"], row["full_text"]))
    return tweets


def run_embedding(
    conn: sqlite3.Connection,
    sample: int | None = None,
    resume: bool = False,
    csv_path: Path | None = None,
) -> int:
    """Embed tweets and store in DB.

    Reads from CSV if csv_path is provided, otherwise from tweets table.
    When using CSV, also creates a lightweight tweets table for rollup joins.

    Returns count of newly embedded tweets.
    """
    ensure_tables(conn)

    # Get embedding dimension
    dim = get_embedding_dim()
    logger.info("Embedding model: %s, dimension: %d", EMBEDDING_MODEL, dim)

    # Get tweets to embed
    if csv_path:
        logger.info("Loading tweets from CSV: %s", csv_path)
        csv_rows = load_tweets_from_csv(csv_path)
        # Create a lightweight tweets table for rollup joins
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                full_text TEXT
            )
        """)
        conn.executemany(
            "INSERT OR IGNORE INTO tweets (tweet_id, account_id, full_text) VALUES (?, ?, ?)",
            csv_rows,
        )
        conn.commit()
        tweets = [(tid, text) for tid, _, text in csv_rows]
        logger.info("Loaded %d tweets from CSV", len(tweets))
    elif sample:
        tweets = conn.execute(
            "SELECT tweet_id, full_text FROM tweets "
            "WHERE full_text IS NOT NULL AND full_text != '' "
            "ORDER BY RANDOM() LIMIT ?",
            (sample,),
        ).fetchall()
    else:
        tweets = conn.execute(
            "SELECT tweet_id, full_text FROM tweets "
            "WHERE full_text IS NOT NULL AND full_text != '' "
            "ORDER BY tweet_id",
        ).fetchall()

    logger.info("Total tweets to consider: %d", len(tweets))

    # Skip already embedded
    if resume:
        already = get_already_embedded(conn)
        tweets = [(tid, text) for tid, text in tweets if tid not in already]
        logger.info("After resume filter: %d remaining (%d already done)",
                     len(tweets), len(already))
    elif not sample:
        already = get_already_embedded(conn)
        if already:
            logger.info("Found %d existing embeddings. Use --resume to skip them.",
                         len(already))

    total = len(tweets)
    embedded = 0
    t_start = time.time()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = tweets[batch_start:batch_start + BATCH_SIZE]
        ids = [tid for tid, _ in batch]
        texts = [text[:MAX_TWEET_CHARS] for _, text in batch]

        try:
            embeddings = embed_batch(texts)
        except Exception as e:
            logger.error("Embedding batch failed at offset %d: %s", batch_start, e)
            # Save progress and retry after delay
            conn.commit()
            time.sleep(5)
            try:
                embeddings = embed_batch(texts)
            except Exception as e2:
                logger.error("Retry failed: %s. Stopping.", e2)
                break

        # Store
        for tid, emb in zip(ids, embeddings):
            conn.execute(
                "INSERT OR IGNORE INTO tweet_embedding (tweet_id, embedding, model) "
                "VALUES (?, ?, ?)",
                (tid, embedding_to_blob(emb), EMBEDDING_MODEL),
            )
        embedded += len(batch)

        # Checkpoint
        if embedded % CHECKPOINT_EVERY < BATCH_SIZE:
            conn.commit()
            elapsed = time.time() - t_start
            rate = embedded / elapsed
            eta_hrs = (total - embedded) / rate / 3600 if rate > 0 else 0
            logger.info(
                "  %d/%d (%.1f%%) — %.0f tweets/sec — ETA %.1fh",
                embedded, total, 100 * embedded / total, rate, eta_hrs,
            )

    conn.commit()
    elapsed = time.time() - t_start
    logger.info(
        "Embedding complete: %d tweets in %.1f min (%.0f/sec)",
        embedded, elapsed / 60, embedded / elapsed if elapsed > 0 else 0,
    )
    return embedded


# ── Clustering ──────────────────────────────────────────────────────────

def run_clustering(
    conn: sqlite3.Connection,
    scales: list[int] | None = None,
) -> None:
    """K-means clustering at multiple scales on stored embeddings.

    Stores cluster assignments in tweet_cluster table.
    """
    from sklearn.cluster import MiniBatchKMeans

    if scales is None:
        scales = [2, 4, 8, 16, 32, 64, 128, 256]

    ensure_tables(conn)

    # Load all embeddings
    rows = conn.execute(
        "SELECT tweet_id, embedding FROM tweet_embedding"
    ).fetchall()
    if not rows:
        logger.error("No embeddings found. Run embedding first.")
        return

    # Detect dimension from first blob
    dim = len(rows[0][1]) // 4  # float32 = 4 bytes
    logger.info("Loading %d embeddings (dim=%d)...", len(rows), dim)

    ids = [r[0] for r in rows]
    X = np.zeros((len(rows), dim), dtype=np.float32)
    for i, (_, blob) in enumerate(rows):
        X[i] = blob_to_embedding(blob, dim)

    # L2 normalize for cosine-like clustering
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1
    X_norm = X / norms

    logger.info("Clustering at scales: %s", scales)

    for k in scales:
        if k > len(ids):
            logger.warning("k=%d > n_tweets=%d, skipping", k, len(ids))
            continue

        logger.info("  k=%d ...", k)
        t0 = time.time()

        km = MiniBatchKMeans(
            n_clusters=k,
            batch_size=min(10000, len(ids)),
            n_init=3,
            random_state=42,
        )
        labels = km.fit_predict(X_norm)
        distances = km.transform(X_norm).min(axis=1)

        # Store
        conn.execute("DELETE FROM tweet_cluster WHERE k = ?", (k,))
        conn.executemany(
            "INSERT INTO tweet_cluster (tweet_id, k, cluster_id, distance) "
            "VALUES (?, ?, ?, ?)",
            [(ids[i], k, int(labels[i]), float(distances[i]))
             for i in range(len(ids))],
        )
        conn.execute(
            "INSERT OR REPLACE INTO cluster_run (k, inertia, n_tweets) "
            "VALUES (?, ?, ?)",
            (k, float(km.inertia_), len(ids)),
        )
        conn.commit()

        elapsed = time.time() - t0
        logger.info(
            "    k=%d: inertia=%.2f, %.1fs",
            k, km.inertia_, elapsed,
        )

    logger.info("Clustering complete at %d scales.", len(scales))


# ── Account rollup ──────────────────────────────────────────────────────

def rollup_account_histograms(conn: sqlite3.Connection) -> None:
    """Roll up tweet cluster memberships to account-level histograms.

    For each (account, k), compute the distribution of their authored tweets
    across clusters. Store in account_cluster_histogram table.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_cluster_histogram (
            account_id TEXT NOT NULL,
            k INTEGER NOT NULL,
            histogram_json TEXT NOT NULL,
            n_tweets INTEGER NOT NULL,
            PRIMARY KEY (account_id, k)
        )
    """)
    conn.commit()

    # Get all scales
    scales = [r[0] for r in conn.execute(
        "SELECT DISTINCT k FROM cluster_run ORDER BY k"
    ).fetchall()]

    if not scales:
        logger.error("No cluster runs found. Run clustering first.")
        return

    for k in scales:
        logger.info("Rolling up account histograms for k=%d...", k)

        rows = conn.execute("""
            SELECT t.account_id, tc.cluster_id, COUNT(*) as cnt
            FROM tweet_cluster tc
            JOIN tweets t ON t.tweet_id = tc.tweet_id
            WHERE tc.k = ?
            GROUP BY t.account_id, tc.cluster_id
        """, (k,)).fetchall()

        # Build per-account histograms
        accounts: dict[str, dict[int, int]] = {}
        for aid, cid, cnt in rows:
            if aid not in accounts:
                accounts[aid] = {}
            accounts[aid][cid] = cnt

        # Normalize and store
        for aid, hist in accounts.items():
            total = sum(hist.values())
            normalized = {str(cid): round(cnt / total, 6) for cid, cnt in hist.items()}
            conn.execute(
                "INSERT OR REPLACE INTO account_cluster_histogram "
                "(account_id, k, histogram_json, n_tweets) VALUES (?, ?, ?, ?)",
                (aid, k, json.dumps(normalized), total),
            )
        conn.commit()
        logger.info("  k=%d: %d accounts", k, len(accounts))

    logger.info("Account rollup complete.")


# ── Cross-scale alignment ───────────────────────────────────────────────

def analyze_cross_scale(conn: sqlite3.Connection) -> None:
    """Analyze how clusters at k nest inside clusters at k/2."""
    scales = [r[0] for r in conn.execute(
        "SELECT DISTINCT k FROM cluster_run ORDER BY k"
    ).fetchall()]

    if len(scales) < 2:
        logger.error("Need at least 2 scales for cross-scale analysis.")
        return

    for i in range(len(scales) - 1):
        k_parent = scales[i]
        k_child = scales[i + 1]

        # For each child cluster, find its dominant parent cluster
        rows = conn.execute("""
            SELECT child.cluster_id as child_c, parent.cluster_id as parent_c, COUNT(*) as cnt
            FROM tweet_cluster child
            JOIN tweet_cluster parent ON child.tweet_id = parent.tweet_id
            WHERE child.k = ? AND parent.k = ?
            GROUP BY child.cluster_id, parent.cluster_id
        """, (k_child, k_parent)).fetchall()

        # Build confusion matrix
        child_totals: dict[int, int] = {}
        child_parent: dict[int, dict[int, int]] = {}
        for cc, pc, cnt in rows:
            child_totals[cc] = child_totals.get(cc, 0) + cnt
            if cc not in child_parent:
                child_parent[cc] = {}
            child_parent[cc][pc] = cnt

        # Measure nesting quality: what fraction of each child cluster
        # comes from a single parent?
        purities = []
        for cc, parents in child_parent.items():
            total = child_totals[cc]
            dominant = max(parents.values())
            purities.append(dominant / total)

        avg_purity = np.mean(purities) if purities else 0
        print(f"  k={k_parent}→{k_child}: avg purity={avg_purity:.3f} "
              f"(1.0 = perfect nesting, {len(purities)} child clusters)")


# ── Main ────────────────────────────────────────────────────────────────

def main():
    global LMSTUDIO_URL, EMBEDDING_MODEL, BATCH_SIZE

    parser = argparse.ArgumentParser(
        description="Embed tweets and cluster at multiple scales"
    )
    parser.add_argument("--db", type=Path, required=True, help="Path to DB (archive_tweets.db or new output DB)")
    parser.add_argument("--csv", type=Path, help="Load tweets from CSV instead of DB tweets table")
    parser.add_argument("--sample", type=int, help="Embed only N random tweets (for testing)")
    parser.add_argument("--resume", action="store_true", help="Skip already-embedded tweets")
    parser.add_argument("--cluster-only", action="store_true", help="Skip embedding, just cluster")
    parser.add_argument("--rollup-only", action="store_true", help="Skip embed+cluster, just rollup")
    parser.add_argument("--analyze-only", action="store_true", help="Just print cross-scale analysis")
    parser.add_argument("--scales", type=str, default="2,4,8,16,32,64,128,256",
                        help="Comma-separated k values for clustering")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--lmstudio-url", type=str, default=LMSTUDIO_URL)
    parser.add_argument("--model", type=str, default=EMBEDDING_MODEL)
    args = parser.parse_args()

    LMSTUDIO_URL = args.lmstudio_url
    EMBEDDING_MODEL = args.model
    BATCH_SIZE = args.batch_size

    scales = [int(x) for x in args.scales.split(",")]

    conn = sqlite3.connect(str(args.db))
    ensure_tables(conn)

    if args.analyze_only:
        analyze_cross_scale(conn)
        conn.close()
        return

    if args.rollup_only:
        rollup_account_histograms(conn)
        conn.close()
        return

    if not args.cluster_only:
        run_embedding(conn, sample=args.sample, resume=args.resume, csv_path=args.csv)

    run_clustering(conn, scales=scales)
    rollup_account_histograms(conn)
    analyze_cross_scale(conn)

    # Summary
    n_emb = conn.execute("SELECT COUNT(*) FROM tweet_embedding").fetchone()[0]
    n_clusters = conn.execute("SELECT COUNT(DISTINCT k) FROM cluster_run").fetchone()[0]
    n_accounts = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM account_cluster_histogram"
    ).fetchone()[0]
    print(f"\n{'='*60}")
    print(f"Multi-scale tweet clustering complete")
    print(f"  Embeddings:  {n_emb:,}")
    print(f"  Scales:      {n_clusters} ({','.join(str(s) for s in scales)})")
    print(f"  Accounts:    {n_accounts}")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    main()
