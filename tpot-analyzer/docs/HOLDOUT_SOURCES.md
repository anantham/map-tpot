# Holdout & Ground Truth Sources

*Last updated: 2026-03-24*

Cross-validation ground truth for measuring recall of the community map.
Each source provides an independent signal of TPOT community membership.

## Sources

| Source | Table | Count | Description |
|--------|-------|-------|-------------|
| **Orange TPOT Directory** | `tpot_directory_holdout` (source='orange_directory') | 283 | Community-recognized TPOT accounts from the Orange directory |
| **Strangest Loop Directory** | `tpot_directory_holdout` (source='strangest_loop') | 106 | Rationalist/post-rat ecosystem directory |
| **Aditya's Curated List** | `shadow_list_member` (list_id='1788441465326064008') | 219 | X list: https://x.com/i/lists/1788441465326064008. Curated by @adityaarpitha. Includes 184 original + 35 manually added accounts. |
| **Ego Follows** | `account_following` (account_id='261659859') | 1,457 | Accounts @adityaarpitha follows — "TPOT-adjacent from my perspective" |

## DB Locations

- `tpot_directory_holdout` → `data/archive_tweets.db`
- `shadow_list_member` → `data/cache.db`
- `account_following` → `data/archive_tweets.db`

## Multi-Source Confidence

An account appearing in multiple sources is stronger evidence of TPOT membership:

| Sources | Accounts | Interpretation |
|---------|----------|---------------|
| 4 | 1 | Highest confidence — recognized by all communities |
| 3 | 22 | Very high — cross-community consensus |
| 2 | 108 | High — corroborated by independent sources |
| 1 | 1,663 | Moderate — single source, needs labeling to confirm |

## Recall Measurement

Run: `.venv/bin/python3 -m scripts.verify_holdout_recall`

Current recall (2026-03-24, pre-Round-1):
- Orange: 42/209 = 20%
- Strangest Loop: 44/99 = 44%
- Pirkowski List: 20/184 = 11%
- Ego Follows: 118/1,457 = 8%
- **Combined: 152/1,794 = 8.5%**

## Highest-Confidence Misses

Accounts in 3+ sources but NOT in our labeled or propagated set (priority targets for labeling):

1. @gptbrooke — orange_directory, pirkowski_list, strangest_loop
2. @embryosophy — ego_follows, orange_directory, strangest_loop
3. @touchmoonflower — ego_follows, orange_directory, strangest_loop
4. @sonikudzu — ego_follows, orange_directory, pirkowski_list
5. @soundrotator — ego_follows, orange_directory, pirkowski_list
6. @Duderichy — ego_follows, orange_directory, pirkowski_list
7. @RosieCampbell — ego_follows, orange_directory, pirkowski_list

## Chrome Audit Log

Tweet-level verification is tracked in `chrome_audit_log` (archive_tweets.db):

```sql
SELECT verdict, COUNT(*) FROM chrome_audit_log GROUP BY verdict;
-- correct: 23, corrected: 33, flagged: 1

-- Find unaudited tweets for an account:
SELECT tt.tweet_id FROM tweet_tags tt
WHERE tt.category = 'bits'
AND tt.tweet_id NOT IN (SELECT tweet_id FROM chrome_audit_log)
AND tt.tweet_id IN (SELECT CAST(t.tweet_id AS TEXT) FROM tweets t WHERE t.account_id = ?);
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/verify_holdout_recall.py` | Measure recall against all sources |
| `scripts/resolve_directory_handles.py` | Resolve directory handles → account_ids |
| `scripts/fetch_following_for_frontier.py` | Fetch outbound edges for frontier accounts |
| `scripts/active_learning.py --measure` | Full pipeline: rollup → seeds → propagate → recall |

## Adding New Sources

1. Insert accounts into appropriate table with source tag
2. Resolve handles to account_ids via `resolve_directory_handles.py`
3. Re-run `verify_holdout_recall.py` to update recall numbers
4. Update this doc with new source + counts
