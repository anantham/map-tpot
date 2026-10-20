#!/usr/bin/env python3
"""Read-only, fixed-protocol development recovery diagnostic; aggregate stdout only.

Use --archive-db, --tag-db, --ego, and optional --tags dharma tpot. No network,
DB/schema writes, paid models, outcome-dependent tuning, or discovery-deck reads.
Each document contains up to 20 recent nonempty, non-RT posts, merged from the
top 20 per source (tweets/full_text and enriched_tweets/text), deduped by tweet
ID; archive text wins duplicates. ISO and Twitter dates are parsed to UTC;
missing/unparseable dates sort last, then tweet-ID string ascending. Replies,
URLs, mentions, and stop words remain. At least 3 posts are required.

Each leave-one-positive-out fold ranks the SAME content-covered universe for
all methods: accounts reached by remaining positives, excluding those anchors
and all negatives. Content-ineligible heldouts are explicitly omitted; eligible
but unreachable heldouts are misses (rank N+1, percentile 100, not Top20).
TF-IDF is transductive: fit once/tag on unlabeled candidate docs plus covered
positives. The heldout label never enters its positive centroid. This measures
known-member recovery under severe capture bias, NOT novel-discovery precision.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import statistics
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, path: Path):
    """Load existing pure modules without importing unrelated package services."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _labels(path: Path, ego: str, tags: list[str]) -> dict:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        result = {}
        for tag in tags:
            rows = conn.execute(
                "SELECT account_id,polarity FROM account_tags WHERE ego=? AND tag_key=?",
                (ego, tag.strip().casefold()),
            ).fetchall()
            if any(type(p) is not int or p not in (-1, 1) for _, p in rows):
                raise ValueError(f"{tag}: invalid source label polarity")
            pos = {str(a) for a, p in rows if p == 1}
            neg = {str(a) for a, p in rows if p == -1}
            if len(pos) < 2 or pos & neg:
                raise ValueError(f"{tag}: need >=2 disjoint positive anchors")
            result[tag] = (pos, neg)
        return result


def _content(conn, wanted: set[str]) -> tuple[dict, dict, dict, set, set, dict]:
    metrics = dict(rows_loaded_capped20_per_source=0, duplicate_tweet_ids_between_sources=0,
                   invalid_ids=0, timestamp_rows_parsed=0, timestamp_parse_failures_or_missing=0)

    def post_time(value):
        metrics["timestamp_rows_parsed"] += 1
        try:
            if not value:
                raise ValueError("missing timestamp")
            try:
                date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                date = parsedate_to_datetime(str(value))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return date.timestamp()
        except (ValueError, TypeError):
            metrics["timestamp_parse_failures_or_missing"] += 1
            return -1e20

    conn.create_function("post_time", 1, post_time, deterministic=True)
    authored = {str(r[0]) for r in conn.execute("SELECT DISTINCT account_id FROM tweets")}
    enriched = {str(r[0]) for r in conn.execute("SELECT DISTINCT account_id FROM enriched_tweets")}
    relevant = sorted(wanted & (authored | enriched))
    corpus, counts, sources = {}, {}, {}
    for aid in relevant:
        by_id = {}
        for table, column, accounts in (("tweets", "full_text", authored),
                                        ("enriched_tweets", "text", enriched)):
            if aid not in accounts:
                continue
            query = (f"SELECT tweet_id,{column},post_time(created_at) AS stamp FROM {table} "
                     f"WHERE account_id=? AND {column} IS NOT NULL "
                     f"AND length(trim({column}))>0 AND upper(ltrim({column})) NOT LIKE 'RT @%' "
                     "ORDER BY stamp DESC,tweet_id ASC LIMIT 20")
            for tid, text, stamp in conn.execute(query, (aid,)):
                metrics["rows_loaded_capped20_per_source"] += 1
                if not tid:
                    metrics["invalid_ids"] += 1
                    continue
                tid = str(tid)
                if tid in by_id:
                    metrics["duplicate_tweet_ids_between_sources"] += 1
                    continue
                by_id[tid] = (stamp, text, table)
        chosen = sorted(by_id.items(), key=lambda r: (-r[1][0], r[0]))[:20]
        counts[aid] = len(chosen)
        sources[aid] = {r[1][2] for r in chosen}
        if len(chosen) >= 3:
            corpus[aid] = "\n".join(r[1][1] for r in chosen)
    metrics.update(any_posts_accounts_archive=len(authored), any_posts_accounts_enriched=len(enriched),
                   any_posts_accounts_union=len(authored | enriched),
                   relevant_accounts_with_any_source=len(relevant), accounts_meeting_3_posts_total=len(corpus))
    return corpus, counts, sources, authored, enriched, metrics


def _summary(rows: list, universes: list[int], positive_count: int) -> dict:
    return dict(eligible_content_covered_folds=len(rows), omitted_lt3_posts_folds=positive_count-len(rows),
                nonempty_candidate_universe_folds=sum(n > 0 for n in universes),
                recovered_target_in_universe=sum(r[2] for r in rows),
                unrecovered_target_not_in_universe=sum(not r[2] for r in rows),
                top20_count=sum(r[3] for r in rows), top20_fraction_eligible=sum(r[3] for r in rows)/len(rows),
                mean_rank_missing_N_plus_1=statistics.mean(r[0] for r in rows),
                median_rank_missing_N_plus_1=statistics.median(r[0] for r in rows),
                mean_percentile_missing_100=statistics.mean(r[1] for r in rows))


def _evaluate(tag, pos, neg, graph, corpus, scorer) -> dict:
    started = time.perf_counter()
    edges, claims, pool = graph
    available, positive_covered = pool & corpus.keys(), pos & corpus.keys()
    if len(positive_covered) < 3 or len(available) < 20:
        return dict(tag=tag, status="insufficient_coverage", covered_positives=len(positive_covered),
                    covered_candidates=len(available))
    doc_ids = sorted(available | positive_covered)
    index = {a: i for i, a in enumerate(doc_ids)}
    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=20000,
                                 lowercase=True, stop_words=None, sublinear_tf=False, norm="l2")
    matrix = vectorizer.fit_transform([corpus[a] for a in doc_ids])
    zero_docs = int(np.sum(np.asarray(matrix.getnnz(axis=1)).ravel() == 0))
    if zero_docs:
        return dict(tag=tag, status="zero_feature_documents", count=zero_docs)
    metrics = {name: [] for name in ("raw_graph_support", "tfidf_centroid_cosine", "rrf60")}
    universes = []
    for heldout in sorted(positive_covered):
        train, content_train = pos - {heldout}, positive_covered - {heldout}
        result = scorer.rank_follow_candidates(train, edges, claims)
        candidates = [r for r in result.candidates if r.account_id not in train | neg and r.account_id in corpus]
        ids = sorted(r.account_id for r in candidates)
        universes.append(len(ids))
        raw = {r.account_id: r.raw_support for r in candidates}
        centroid = normalize(np.asarray(matrix[[index[a] for a in sorted(content_train)]].mean(axis=0)))
        cosine = np.asarray(matrix[[index[a] for a in ids]] @ centroid.T).ravel()
        text = dict(zip(ids, cosine))
        graph_order = sorted(ids, key=lambda a: (-raw[a], a))
        text_order = sorted(ids, key=lambda a: (-text[a], a))
        graph_ranks = {a: i+1 for i, a in enumerate(graph_order)}
        text_ranks = {a: i+1 for i, a in enumerate(text_order)}
        rrf_order = sorted(ids, key=lambda a: (-(1/(60+graph_ranks[a])+1/(60+text_ranks[a])), a))
        for name, order in zip(metrics, (graph_order, text_order, rrf_order)):
            positions = {a: i+1 for i, a in enumerate(order)}
            found = heldout in positions
            rank = positions.get(heldout, len(ids)+1)
            metrics[name].append((rank, 100*rank/len(ids) if found and ids else 100.0, found, found and rank <= 20))
    return dict(tag=tag, status="complete", vocabulary_features=matrix.shape[1], vectorizer_documents=matrix.shape[0],
                matrix_nonzeros=matrix.nnz, zero_feature_documents=zero_docs,
                fold_candidate_count_min=min(universes), fold_candidate_count_max=max(universes),
                graph_seed_count_range=[len(pos)-1]*2, content_seed_count_range=[len(positive_covered)-1]*2,
                methods={name: _summary(rows, universes, len(pos)) for name, rows in metrics.items()},
                tag_model_wall_seconds=time.perf_counter()-started)


def main() -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-db", type=Path, required=True)
    parser.add_argument("--tag-db", type=Path, required=True)
    parser.add_argument("--ego", required=True)
    parser.add_argument("--tags", nargs="+", default=["dharma", "tpot"])
    parser.add_argument("--timeout-seconds", type=float, default=150, help="read-phase wall bound, not a model parameter")
    args = parser.parse_args()
    scorer = _module("content_recovery_scorer", ROOT / "src/graph/source_selectivity.py")
    archive = _module("content_recovery_archive", ROOT / "src/data/follow_frontier_archive.py")
    labels = _labels(args.tag_db, args.ego, args.tags)
    graphs, wanted = {}, set()
    with closing(archive.open_archive_readonly(args.archive_db)) as conn:
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.set_progress_handler(lambda: int(time.perf_counter()-started > args.timeout_seconds), 100000)
        for tag, (pos, neg) in labels.items():
            edges = archive.load_follow_edges(conn, pos | neg)
            claims = archive.load_claimed_following_counts(conn, pos | neg)
            pool = {r.account_id for r in scorer.rank_follow_candidates(pos, edges, claims).candidates} - neg
            graphs[tag] = (edges, claims, pool)
            wanted |= pool | pos
        corpus, counts, sources, authored, enriched, metrics = _content(conn, wanted)
    coverage = []
    for tag, (pos, _) in labels.items():
        pool = graphs[tag][2]
        available, positives = pool & corpus.keys(), pos & corpus.keys()
        coverage.append(dict(tag=tag, positives=len(pos), positive_content_covered=len(positives),
                             positive_omitted_lt3_posts=len(pos-positives), outgoing_candidate_pool=len(pool),
                             candidate_content_covered=len(available), candidate_coverage_fraction=len(available)/len(pool) if pool else None,
                             candidate_has_archive_source=sum(a in authored for a in available),
                             candidate_has_enriched_source=sum(a in enriched for a in available),
                             candidate_selected_archive_source=sum("tweets" in sources[a] for a in available),
                             candidate_selected_enriched_source=sum("enriched_tweets" in sources[a] for a in available),
                             positive_has_archive_source=sum(a in authored for a in positives),
                             positive_has_enriched_source=sum(a in enriched for a in positives),
                             selected_posts_for_candidate_documents=sum(counts[a] for a in available),
                             selected_posts_for_positive_documents=sum(counts[a] for a in positives)))
    print("✓ Source reads completed with mode=ro, query_only=ON and a fixed archive transaction", flush=True)
    print(json.dumps(dict(phase="coverage", reports=coverage, **metrics, coverage_wall_seconds=time.perf_counter()-started), indent=2), flush=True)
    results = [_evaluate(tag, pos, neg, graphs[tag], corpus, scorer) for tag, (pos, neg) in labels.items()]
    for result in results:
        ok = result["status"] == "complete"
        print(f"{'✓' if ok else '✗'} {result['tag']}: {result['status']}; computation status, not scientific validation")
    print(json.dumps(dict(phase="fixed_development_content_LOO", timestamp_utc=datetime.now(timezone.utc).isoformat(),
                          protocol=__doc__, python=sys.version.split()[0],
                          tfidf="word unigram+bigram; min_df=2; max_features=20000; lowercase; no stopword removal; linear tf; l2; remaining sklearn defaults",
                          centroid="mean l2 document vectors of remaining content-covered positives, then l2 normalize",
                          graph="distinct support from ALL remaining positive anchors, including content-uncovered anchors",
                          rrf="1/(60+graph_rank)+1/(60+content_rank); one-based ranks",
                          ties="descending score then ascending account-ID string, no secondary signal",
                          percentile="100 * one-based rank / fold universe size, lower better; eligible misses=100",
                          results=results, total_script_wall_seconds=time.perf_counter()-started), indent=2))
    print("Next: interpret coverage and recovery descriptively; do not infer discovery precision or tune against these outcomes.")
    return 0 if all(r["status"] == "complete" for r in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (sqlite3.Error, ValueError, OSError) as exc:
        print(f"✗ Content recovery stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
