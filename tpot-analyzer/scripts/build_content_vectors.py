#!/usr/bin/env python3
"""
Topic modeling on liked tweet texts — CT1 content vectors.

Discovers macro-interest vectors from what each seed account likes.
Each account becomes a "document" (all their liked texts concatenated),
then TF-IDF + NMF extracts latent topics.

Output tables:
    content_topic          — topic_idx, top 15 words, created_at
    account_content_profile — account_id, topic_idx, weight (sums to 1)

Usage:
    .venv/bin/python3 -m scripts.build_content_vectors
    .venv/bin/python3 -m scripts.build_content_vectors --n-topics 25
    .venv/bin/python3 -m scripts.build_content_vectors --n-topics 25 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Schema ───────────────────────────────────────────────────────────────────

CREATE_CONTENT_TOPIC = """
CREATE TABLE IF NOT EXISTS content_topic (
    topic_idx   INTEGER PRIMARY KEY,
    top_words   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""

CREATE_ACCOUNT_CONTENT_PROFILE = """
CREATE TABLE IF NOT EXISTS account_content_profile (
    account_id  TEXT NOT NULL,
    topic_idx   INTEGER NOT NULL,
    weight      REAL NOT NULL,
    PRIMARY KEY (account_id, topic_idx)
);
"""


# ── Data loading ─────────────────────────────────────────────────────────────

def load_account_documents(db_path: Path) -> tuple[list[str], list[str], list[str]]:
    """
    Stream liked tweets from DB, concatenate per account.

    Returns (account_ids, usernames, documents) where each document is the
    concatenated full_text of all likes for that account.

    Uses ORDER BY liker_account_id so we can stream without loading all 17M
    rows into memory at once — we accumulate one account's texts at a time.
    """
    log.info("Loading liked tweets from %s ...", db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    cursor = conn.execute(
        "SELECT liker_account_id, liker_username, full_text "
        "FROM likes "
        "WHERE full_text IS NOT NULL "
        "ORDER BY liker_account_id"
    )

    account_ids: list[str] = []
    usernames: list[str] = []
    documents: list[str] = []

    current_id: str | None = None
    current_username: str = ""
    current_texts: list[str] = []
    row_count = 0

    for aid, uname, text in cursor:
        row_count += 1
        if row_count % 2_000_000 == 0:
            log.info("  ... streamed %dM rows", row_count // 1_000_000)

        if aid != current_id:
            # Flush previous account
            if current_id is not None and current_texts:
                account_ids.append(current_id)
                usernames.append(current_username)
                documents.append(" ".join(current_texts))
            current_id = aid
            current_username = uname
            current_texts = []

        current_texts.append(text)

    # Flush last account
    if current_id is not None and current_texts:
        account_ids.append(current_id)
        usernames.append(current_username)
        documents.append(" ".join(current_texts))

    conn.close()
    log.info(
        "Loaded %d rows → %d account documents",
        row_count, len(account_ids),
    )
    return account_ids, usernames, documents


# ── Topic modeling ───────────────────────────────────────────────────────────

def build_topics(
    documents: list[str],
    n_topics: int = 25,
    max_features: int = 10_000,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    TF-IDF + NMF topic modeling.

    Returns:
        W: (n_docs, n_topics) — document-topic weights
        H: (n_topics, n_features) — topic-word weights
        feature_names: vocabulary list
    """
    log.info(
        "Building TF-IDF (max_features=%d) on %d documents ...",
        max_features, len(documents),
    )
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        min_df=5,
        max_df=0.8,
        stop_words="english",
        sublinear_tf=True,
        token_pattern=r"(?u)\b[a-zA-Z]{3,}\b",  # words only, 3+ chars
    )
    tfidf = vectorizer.fit_transform(documents)
    feature_names = vectorizer.get_feature_names_out().tolist()
    log.info("TF-IDF matrix: %s  (nnz=%d)", tfidf.shape, tfidf.nnz)

    log.info("Running NMF with k=%d ...", n_topics)
    nmf = NMF(
        n_components=n_topics,
        random_state=42,
        max_iter=500,
        init="nndsvda",
    )
    W = nmf.fit_transform(tfidf)
    H = nmf.components_
    log.info(
        "NMF converged in %d iterations (reconstruction error: %.4f)",
        nmf.n_iter_, nmf.reconstruction_err_,
    )
    return W, H, feature_names


def extract_top_words(
    H: np.ndarray,
    feature_names: list[str],
    n_top: int = 15,
) -> list[list[str]]:
    """For each topic row in H, return the top-n words by weight."""
    topics = []
    for row in H:
        top_idx = row.argsort()[::-1][:n_top]
        topics.append([feature_names[i] for i in top_idx])
    return topics


def normalize_weights(W: np.ndarray) -> np.ndarray:
    """Normalize each row of W to sum to 1 (topic distribution per account)."""
    row_sums = W.sum(axis=1, keepdims=True)
    # Avoid division by zero for accounts with no signal
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    return W / row_sums


# ── Persistence ──────────────────────────────────────────────────────────────

def save_to_db(
    db_path: Path,
    account_ids: list[str],
    W_norm: np.ndarray,
    topic_words: list[list[str]],
) -> None:
    """Write content_topic and account_content_profile tables."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path))

    conn.execute(CREATE_CONTENT_TOPIC)
    conn.execute(CREATE_ACCOUNT_CONTENT_PROFILE)

    # Clear previous run
    conn.execute("DELETE FROM content_topic")
    conn.execute("DELETE FROM account_content_profile")

    # Insert topics
    for idx, words in enumerate(topic_words):
        conn.execute(
            "INSERT INTO content_topic (topic_idx, top_words, created_at) "
            "VALUES (?, ?, ?)",
            (idx, ", ".join(words), now),
        )

    # Insert account profiles
    n_topics = W_norm.shape[1]
    rows = []
    for i, aid in enumerate(account_ids):
        for t in range(n_topics):
            w = float(W_norm[i, t])
            if w > 1e-6:  # skip near-zero weights
                rows.append((aid, t, w))

    conn.executemany(
        "INSERT INTO account_content_profile (account_id, topic_idx, weight) "
        "VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    log.info(
        "Saved %d topics and %d profile rows to %s",
        len(topic_words), len(rows), db_path.name,
    )


# ── Display ──────────────────────────────────────────────────────────────────

def print_topics(topic_words: list[list[str]]) -> None:
    """Pretty-print each topic with its top words."""
    print("\n" + "=" * 72)
    print(f"  {len(topic_words)} CONTENT TOPICS (top 15 words each)")
    print("=" * 72)
    for idx, words in enumerate(topic_words):
        print(f"\n  Topic {idx:2d}:  {', '.join(words)}")


def print_account_profiles(
    account_ids: list[str],
    usernames: list[str],
    W_norm: np.ndarray,
    topic_words: list[list[str]],
    top_k: int = 3,
    accounts_to_show: list[str] | None = None,
) -> None:
    """Print each account's top-k topics."""
    uname_map = dict(zip(account_ids, usernames))

    if accounts_to_show:
        show_set = set(accounts_to_show)
        indices = [
            i for i, u in enumerate(usernames) if u in show_set
        ]
        if not indices:
            log.warning("None of the requested accounts found in data")
            return
    else:
        # Show top 20 by total engagement (largest W row norm)
        norms = np.linalg.norm(W_norm, axis=1)
        indices = norms.argsort()[::-1][:20]

    print("\n" + "=" * 72)
    print(f"  ACCOUNT CONTENT PROFILES (top {top_k} topics)")
    print("=" * 72)

    for i in indices:
        aid = account_ids[i]
        uname = usernames[i]
        row = W_norm[i]
        top_topics = row.argsort()[::-1][:top_k]

        parts = []
        for t in top_topics:
            if row[t] < 0.01:
                continue
            label = ", ".join(topic_words[t][:5])
            parts.append(f"T{t}={row[t]:.1%} [{label}]")

        profile = "  |  ".join(parts) if parts else "(no signal)"
        print(f"\n  @{uname} ({aid})")
        print(f"    {profile}")


# ── Main ─────────────────────────────────────────────────────────────────────

KNOWN_ACCOUNTS = [
    "RomeoStevens76",
    "repligate",
    "visakanv",
    "eshear",
    "dschorno",
    "QiaochuYuan",
    "adityaarpitha",
    "pee_zombie",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Content topic modeling on liked tweet texts (CT1)",
    )
    parser.add_argument(
        "--n-topics", type=int, default=25,
        help="Number of NMF topics (default: 25)",
    )
    parser.add_argument(
        "--max-features", type=int, default=10_000,
        help="Max TF-IDF vocabulary size (default: 10000)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print topics and profiles but don't write to DB",
    )
    parser.add_argument(
        "--db", type=str, default=str(ARCHIVE_DB),
        help=f"Database path (default: {ARCHIVE_DB})",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("Database not found: %s", db_path)
        sys.exit(1)

    t0 = time.time()

    # 1. Load data
    account_ids, usernames, documents = load_account_documents(db_path)

    # 2. Topic modeling
    W, H, feature_names = build_topics(
        documents,
        n_topics=args.n_topics,
        max_features=args.max_features,
    )

    # 3. Extract results
    topic_words = extract_top_words(H, feature_names, n_top=15)
    W_norm = normalize_weights(W)

    # 4. Display
    print_topics(topic_words)
    print_account_profiles(
        account_ids, usernames, W_norm, topic_words,
        top_k=3,
        accounts_to_show=KNOWN_ACCOUNTS,
    )

    # 5. Save
    if args.dry_run:
        log.info("Dry run — skipping DB write")
    else:
        save_to_db(db_path, account_ids, W_norm, topic_words)

    elapsed = time.time() - t0
    log.info("Done in %.1f seconds", elapsed)


if __name__ == "__main__":
    main()
