# Archive DB Schema Reference

**File:** `data/archive_tweets.db`
**Size:** ~9GB (SQLite)
**Tables:** 58
**Last updated:** 2026-03-28

This document is the canonical "where does X live?" reference for the archive database. Tables are grouped by domain. Row counts are as of 2026-03-28.

---

## Table of Contents

1. [Core Data](#1-core-data)
2. [Follow Graph](#2-follow-graph)
3. [Community Detection (NMF)](#3-community-detection-nmf)
4. [Active Learning / Tweet Labeling](#4-active-learning--tweet-labeling)
5. [Golden Dataset / Evaluation](#5-golden-dataset--evaluation)
6. [Propagation / Band Classification](#6-propagation--band-classification)
7. [Engagement / Signal](#7-engagement--signal)
8. [Content Vectors](#8-content-vectors)
9. [Profile Cache (from API)](#9-profile-cache-from-api)
10. [Holdout / Validation](#10-holdout--validation)
11. [Other / Operational](#11-other--operational)
12. [Key Relationships](#12-key-relationships)
13. [Source of Truth Map](#13-source-of-truth-map)

---

## 1. Core Data

Imported from Community Archive. These are the raw social media artifacts and the foundation for everything else.

### `tweets` (5,553,430 rows)

The primary corpus. Every tweet from every archived account.

| Column | Type | Notes |
|---|---|---|
| tweet_id | TEXT | Primary key |
| account_id | TEXT | Author's account ID |
| username | TEXT | Author's handle at time of fetch |
| full_text | TEXT | Raw tweet text |
| created_at | DATETIME | When tweet was posted |
| reply_to_tweet_id | TEXT | NULL if not a reply |
| reply_to_username | TEXT | NULL if not a reply |
| favorite_count | INTEGER | Likes at time of fetch |
| retweet_count | INTEGER | RTs at time of fetch |
| lang | TEXT | Language code (e.g., "en") |
| is_note_tweet | INTEGER | 1 if extended/note tweet |
| fetched_at | DATETIME | When row was inserted |

**Source of truth for:** all original tweet content and metadata from the archive.

---

### `likes` (17,501,243 rows)

Who liked what. Denormalized: includes the full text of the liked tweet at fetch time.

| Column | Notes |
|---|---|
| liker_account_id | Account that gave the like |
| liker_username | Handle at time of fetch |
| tweet_id | Liked tweet |
| full_text | Text of the liked tweet (snapshot) |
| expanded_url | First URL in tweet, expanded |
| fetched_at | When row was inserted |

**Note:** The liker's `account_id` is the join key, not `username` (handles change). `tweet_id` is not guaranteed to exist in `tweets` (liked tweets may belong to non-archived accounts).

---

### `retweets` (774,266 rows)

Retweet events. Complements `tweets` for RT-specific analysis (e.g., who amplifies whom).

| Column | Notes |
|---|---|
| tweet_id | ID of the RT event itself |
| account_id | Account that retweeted |
| username | Handle at time of fetch |
| rt_of_username | Original author's handle |
| created_at | When the RT was posted |
| fetched_at | When row was inserted |

---

### `profiles` (26,083 rows)

Profile snapshots from the archive import (not the live API cache — see `user_profile_cache` for that).

| Column | Notes |
|---|---|
| account_id | Primary key |
| username | Handle at snapshot time |
| display_name | |
| bio | Profile bio text |
| location | |
| website | |
| created_at | When the Twitter account was created |
| fetched_at | When row was inserted |

---

## 2. Follow Graph

Directed follow relationships between accounts. The backbone for community detection and propagation.

### `account_following` (803,998 rows)

`account_id` follows `following_account_id`.

| Column | Notes |
|---|---|
| account_id | The follower |
| following_account_id | The account being followed |

---

### `account_followers` (1,647,325 rows)

`account_id` is followed by `follower_account_id`. (Inverse of `account_following`.)

| Column | Notes |
|---|---|
| account_id | The account being followed |
| follower_account_id | The follower |

---

### `edge_fetch_state` (7,047 rows)

Tracks pagination state for follow-graph API fetches. Used to resume interrupted crawls.

| Column | Notes |
|---|---|
| account_id | Account whose edges are being fetched |
| username | Handle |
| last_cursor | API cursor for resuming pagination |
| pages_fetched | How many pages retrieved so far |
| edges_stored | How many edges written to DB |
| actual_following | Ground truth total from API |
| is_complete | 1 when fetch is finished |
| updated_at | Last modified |

---

## 3. Community Detection (NMF)

Tables for storing NMF clustering runs, assigning accounts to communities, and managing named community snapshots.

### `community` (16 rows)

The canonical list of named communities. Each row is a community that has been promoted to "production" and given a name, color, and description.

| Column | Notes |
|---|---|
| id | UUID primary key |
| name | Human-readable name (e.g., "LLM-Whisperers") |
| short_name | Stable labeling handle (e.g., "llm-whisperers") |
| description | Community description, updated from labeling evidence |
| color | Hex color for UI |
| seeded_from_run | `run_id` in `community_run` this was seeded from |
| seeded_from_idx | Which NMF component index this maps to |
| created_at | |
| updated_at | |

**Source of truth for:** community identity, names, descriptions, colors.

---

### `community_account` (932 rows)

The production membership table. Which accounts belong to which community, at what weight, and by what method.

| Column | Notes |
|---|---|
| community_id | FK → `community.id` |
| account_id | FK → account |
| weight | Membership weight (0–1) |
| source | How assigned: `nmf`, `llm_ensemble`, `manual`, etc. |
| updated_at | |

**Source of truth for:** "which community does account X belong to?"

---

### `community_run` (5 rows)

Metadata for each NMF factorization run (different k, signal, threshold combinations).

| Column | Notes |
|---|---|
| run_id | Primary key (e.g., "k14-likes-0.1") |
| k | Number of communities |
| signal | What data was factorized (e.g., "follows+likes") |
| threshold | Min weight to count as member |
| account_count | How many accounts in this run |
| notes | Free-text notes |
| created_at | |

---

### `community_membership` (4,734 rows)

Raw NMF output: every account's weight in every component for each run. Used to re-seed `community_account`.

| Column | Notes |
|---|---|
| run_id | FK → `community_run` |
| account_id | |
| community_idx | 0-indexed component number |
| weight | NMF weight |

---

### `community_definition` (2,740 rows)

What features (accounts, hashtags, URLs) most define each NMF component. Useful for interpreting what a community "means."

| Column | Notes |
|---|---|
| run_id | FK → `community_run` |
| community_idx | |
| feature_type | e.g., `account`, `hashtag` |
| target | The specific feature value |
| score | Importance score |
| rank | Rank within community (1 = most defining) |

---

### `community_alias` (75 rows)

Alternative names or labels for communities (e.g., prior names, colloquial names).

| Column | Notes |
|---|---|
| community_id | FK → `community.id` |
| alias | The alternate name |
| context | Why this alias exists |
| created_at | |

---

### `community_branch` (1 row)

Named branches of the community taxonomy (like git branches). Supports experimental reorganizations without disturbing production.

| Column | Notes |
|---|---|
| id | UUID |
| name | Branch name |
| description | |
| base_run_id | Which `community_run` this branch started from |
| is_active | 1 for the active branch |
| created_at / updated_at | |

---

### `community_snapshot` (4 rows)

Point-in-time snapshots of community state within a branch (like git commits).

| Column | Notes |
|---|---|
| id | UUID |
| branch_id | FK → `community_branch.id` |
| name | Snapshot label |
| created_at | |

---

### `community_snapshot_data` (2,553 rows)

The actual data (memberships, weights) stored in each snapshot. JSONB-style: `kind` identifies the entity type.

| Column | Notes |
|---|---|
| snapshot_id | FK → `community_snapshot.id` |
| kind | e.g., `community_account`, `community` |
| data | JSON blob |

---

## 4. Active Learning / Tweet Labeling

Tables supporting the active learning pipeline: fetching tweets for unlabeled accounts, tagging them, and computing community "bits" from the evidence.

### `enriched_tweets` (1,670 rows)

Tweets fetched via the live API (not archive import) for active learning candidates. Richer metadata than `tweets`.

| Column | Notes |
|---|---|
| tweet_id | Primary key |
| account_id | Author |
| username | Handle |
| text | Tweet text |
| like_count / retweet_count / reply_count / view_count | Engagement metrics |
| created_at | |
| lang | |
| is_reply | Boolean |
| in_reply_to_user | Handle of the user being replied to |
| has_media | Boolean |
| mentions_json | JSON list of mentioned handles |
| fetch_source | How this was fetched (e.g., "timeline", "search") |
| fetch_query | The query used |
| fetched_at | |

---

### `enrichment_log` (101 rows)

Audit log of active learning fetch runs — tracks cost per account.

| Column | Notes |
|---|---|
| id | Auto-increment |
| account_id / username | Target account |
| round | Active learning round number |
| action | What was done (e.g., "fetch_timeline") |
| query | API query used |
| api_calls | Count |
| tweets_fetched | Count |
| estimated_cost | USD |
| created_at | |

---

### `tweet_tags` (19,784 rows)

Human-applied tags on tweets during the labeling process. The raw evidence for community signal.

| Column | Notes |
|---|---|
| tweet_id | FK → `enriched_tweets.tweet_id` |
| tag | The tag value (e.g., "llm-alignment", "qualia-rich") |
| category | Facet: `domain`, `thematic`, `posture`, `bits`, `new-community`, NULL=specific |
| added_by | Reviewer handle |
| created_at | |

---

### `account_community_bits` (591 rows)

Rolled-up evidence: for each (account, community) pair, the total information-theoretic bits of evidence from labeled tweets. **This is the posterior — preferred over NMF weights when available.**

| Column | Notes |
|---|---|
| account_id | |
| community_id | FK → `community.id` |
| total_bits | Sum of bits from all tagged tweets |
| tweet_count | How many tweets contributed |
| pct | Fraction of total bits for this account |
| updated_at | |

**Source of truth for:** community membership when labeling evidence exists. Overrides NMF prior in export.

---

### `thread_context_cache` (310 rows)

Cached thread context (parent tweets, replies) fetched during labeling for context-window assembly.

| Column | Notes |
|---|---|
| tweet_id | The tweet whose context was fetched |
| raw_json | Full API response |
| fetched_at | |

---

### `link_content_cache` (3 rows)

Cached resolved URL content (title, description, body text) for URL-enriched labeling context.

| Column | Notes |
|---|---|
| url_hash | SHA256 of URL, primary key |
| url | Original URL |
| resolved_url | After redirect resolution |
| title / description / body_text | Extracted page content |
| fetched_at | |

---

## 5. Golden Dataset / Evaluation

Tables for tweet-level and account-level ground truth used to evaluate classifiers.

### `curation_split` (5,553,228 rows)

Train/dev/test assignment for every tweet in the corpus. Assigned deterministically via SHA256 hash (70/15/15 split).

| Column | Notes |
|---|---|
| tweet_id | FK → `tweets.tweet_id` |
| axis | Evaluation axis (e.g., "community") |
| split | `train`, `dev`, or `test` |
| assigned_by | `sha256_hash` for deterministic assignment |
| assigned_at | |

**Performance note:** Use `LIMIT 1` existence check before bootstrapping. Do NOT scan all 5.5M rows on every request.

---

### `tweet_label_set` (1,973 rows)

A labeling session for a single tweet: who reviewed it, when, with what context. Supports versioning via `supersedes_label_set_id`.

| Column | Notes |
|---|---|
| id | UUID |
| tweet_id | The labeled tweet |
| axis | Evaluation axis |
| reviewer | Reviewer handle |
| note | Free-text reviewer note |
| context_hash | Hash of context shown to reviewer |
| context_snapshot_json | Full context at time of labeling |
| is_active | 1 for the current label set (superseded ones = 0) |
| created_at | |
| supersedes_label_set_id | FK → prior `tweet_label_set.id` (if correction) |

---

### `tweet_label_prob` (7,892 rows)

The actual label probabilities for each label set. Multi-label: a tweet can have partial probability across multiple communities.

| Column | Notes |
|---|---|
| label_set_id | FK → `tweet_label_set.id` |
| label | Community name or label value |
| probability | Probability assigned to this label |

---

### `model_prediction_set` (0 rows)

Placeholder for model predictions (not yet populated). Mirrors `tweet_label_set` structure.

---

### `model_prediction_prob` (0 rows)

Placeholder for per-label model prediction probabilities. Mirrors `tweet_label_prob`.

---

### `evaluation_run` (0 rows)

Placeholder for tracking evaluation runs (model vs. gold comparison). Not yet populated.

---

### `interpretation_prompt` / `interpretation_run` (0 rows each)

Placeholders for LLM interpretation pass infrastructure. Not yet populated.

---

### `uncertainty_queue` (0 rows)

Intended to track tweets selected for active labeling due to high model uncertainty. Not yet populated.

---

### `account_community_gold_label_set` (167 rows)

Human-verified ground truth at the account level: does account X belong to community Y?

| Column | Notes |
|---|---|
| id | UUID |
| account_id | The account |
| community_id | FK → `community.id` |
| reviewer | Who verified |
| judgment | `member`, `non-member`, `ambiguous` |
| confidence | 0–1 |
| note | Free-text |
| evidence_json | Supporting evidence |
| is_active | 1 for current label (supports corrections) |
| created_at | |

---

### `account_community_gold_split` (167 rows)

Train/dev/test split for the 167 account-level gold labels.

| Column | Notes |
|---|---|
| account_id | |
| split | `train`, `dev`, or `test` |
| assigned_by | |
| assigned_at | |

---

## 6. Propagation / Band Classification

Tables supporting label propagation from seeds to the broader follow graph and the resulting band assignments.

### `account_band` (297,964 rows)

Final propagated classification for all accounts. The output of the label propagation pipeline.

| Column | Notes |
|---|---|
| account_id | |
| band | Classification tier: `core`, `halo`, `bridge`, `noise`, etc. |
| top_community | Name of dominant community |
| top_weight | Weight for that community |
| entropy | Community entropy (low = specialized, high = multi-community) |
| none_weight | Weight on the "None" community |
| degree | Node degree in follow graph |
| created_at | |

**Source of truth for:** which band an account falls into after propagation.

---

### `seed_eligibility` (359 rows)

Per-account eligibility check: should this account be used as a seed for propagation?

| Column | Notes |
|---|---|
| account_id | |
| max_weight | Highest community weight from NMF |
| dominant_community | Which community |
| entropy | |
| concentration | How concentrated the weight distribution is |
| content_agrees | Whether tweet content agrees with NMF assignment |
| eligible | Boolean |
| created_at | |

---

### `frontier_ranking` (8,705 rows)

Candidate accounts prioritized for active learning enrichment. Ranked by information value.

| Column | Notes |
|---|---|
| account_id | |
| band | Current band assignment |
| info_value | Prioritization score |
| top_community | |
| top_weight | |
| degree | |
| in_holdout | Whether this account is in the holdout set |
| created_at | |

---

### `quality_candidates` (256 rows)

Accounts with high TPOT-following concentration — good targets for graph expansion.

| Column | Notes |
|---|---|
| account_id | |
| username | |
| quality_follows | Count of follows pointing to known TPOT accounts |
| total_following | Total following count |
| quality_ratio | quality_follows / total_following |
| in_ego_follows | Whether this account is in the ego network |
| ranked_at | |

---

## 7. Engagement / Signal

Aggregated interaction signals used as features for community detection and ranking.

### `account_engagement_agg` (408,446 rows)

Pre-aggregated engagement between account pairs. **This is the join-safe version of likes/replies/RTs** — use this rather than scanning the raw `likes` table (17.5M rows).

| Column | Notes |
|---|---|
| source_id | The engaging account |
| target_id | The account being engaged with |
| follow_flag | 1 if source follows target |
| like_count | Likes from source to target's tweets |
| reply_count | Replies from source to target |
| rt_count | RTs from source of target's tweets |
| (additional aggregation columns) | |

---

### `signed_reply` (17,362 rows)

Reply relationships with a heuristic positivity/negativity signal.

| Column | Notes |
|---|---|
| replier_id | Account that replied |
| author_id | Account being replied to |
| reply_count | Total replies |
| heuristic | Signed sentiment heuristic |
| created_at | |

---

### `mention_graph` (3,822,341 rows)

Directed mention counts between accounts. Dense signal for community structure.

| Column | Notes |
|---|---|
| source_id | Account that mentioned |
| target_id | Account mentioned |
| mention_count | How many times |
| created_at | |

---

### `quote_graph` (549,285 rows)

Directed quote-tweet counts between accounts.

| Column | Notes |
|---|---|
| source_id | Account that quoted |
| target_id | Account whose tweet was quoted |
| quote_count | How many times |
| created_at | |

---

### `cofollowed_similarity` (16,701 rows)

Pairwise account similarity based on shared followers (Jaccard). Used for clustering refinement.

| Column | Notes |
|---|---|
| account_a / account_b | The pair |
| shared_followers | Count of followers both accounts share |
| jaccard | Jaccard similarity score |
| created_at | |

---

## 8. Content Vectors

Topic models and bio embeddings for content-based community separation.

### `content_topic` (25 rows)

The 25 NMF topics derived from tweet text. Descriptive labels for the topic space.

| Column | Notes |
|---|---|
| topic_idx | 0-indexed topic number |
| top_words | Comma-separated top words for this topic |
| created_at | |

---

### `account_content_profile` (4,071 rows)

Each account's distribution over the 25 content topics.

| Column | Notes |
|---|---|
| account_id | |
| topic_idx | FK → `content_topic.topic_idx` |
| weight | Topic weight for this account |

---

### `bio_embeddings` (15,182 rows)

Bio text embeddings for accounts. Used for content-based community signal (local embedding model).

| Column | Notes |
|---|---|
| account_id | |
| embedding | Binary blob (vector) |
| bio_source | Where the bio came from (`profiles`, `resolved_accounts`, etc.) |
| created_at | |

---

## 9. Profile Cache (from API)

Live API profile data, separate from the archive-imported `profiles` table.

### `user_profile_cache` (9,367 rows)

Profile metadata fetched from the live Twitter API. More current than `profiles`, includes follower/following counts.

| Column | Notes |
|---|---|
| account_id | Primary key |
| username | |
| followers / following / statuses / favourites | Counts at fetch time |
| is_verified / is_blue | Boolean flags |
| description | Bio text |
| location | |
| created_at | When the Twitter account was created |
| raw_json | Full API response |
| fetched_at | When row was inserted |

---

### `user_about_cache` (331 rows)

Extended profile data not available in the standard API (location accuracy, affiliate info, username history).

| Column | Notes |
|---|---|
| account_id | |
| username | |
| account_based_in | Inferred country |
| location_accurate | Boolean |
| affiliate_username | If they're affiliated with another account |
| affiliate_label | Label for that affiliation |
| username_changes | JSON array of prior handles |
| raw_json | Full API response |
| fetched_at | |

---

### `resolved_accounts` (19,144 rows)

Canonical account resolution table: maps account_id to current username and status. Fixes the 854-NULL-username problem.

| Column | Notes |
|---|---|
| account_id | Primary key |
| username | Current handle |
| display_name | |
| status | `active`, `suspended`, `not_found`, `protected` |
| resolved_at | When last resolved |
| bio | Bio text snapshot |

**Source of truth for:** current username for any account_id.

---

## 10. Holdout / Validation

Ground truth sets for measuring recall and precision of the community detection pipeline.

### `tpot_directory_holdout` (389 rows)

Curated list of known TPOT accounts from external sources (directory, Substack, etc.). Used as recall baseline.

| Column | Notes |
|---|---|
| handle | Twitter handle |
| source | Where this came from (`tpot_directory`, `substack`, etc.) |
| display_name | |
| substack_handle | If they have a Substack |
| rt_count | How often they appear in RT chains |
| in_archive | Whether they're in the tweet archive |
| account_id | Resolved account_id (NULL if not resolved) |
| match_type | How account_id was resolved |
| created_at | |

---

### `chrome_audit_log` (57 rows)

Manual tweet-level audit records from Chrome scraping sessions (ground truth for edge cases).

| Column | Notes |
|---|---|
| tweet_id | |
| account_id | Author |
| verdict | Human judgment: `correct`, `incorrect`, `ambiguous` |
| detail | Free-text explanation |
| auditor | Who performed the audit |
| audited_at | |

---

### `chrome_audit_findings` (5 rows)

Summary findings from Chrome audit sessions (not tweet-level, but session-level observations).

| Column | Notes |
|---|---|
| id | |
| audit_date | |
| finding_type | Category of finding |
| detail | Description |
| created_at | |

---

## 11. Other / Operational

### `fetch_log` (413 rows)

Log of archive import fetch operations. One row per account fetch attempt.

| Column | Notes |
|---|---|
| username | |
| account_id | |
| status | `ok`, `error`, `protected`, etc. |
| tweet_count / like_count | What was fetched |
| error_message | If status != ok |
| fetched_at | |

---

### `protected_accounts` (8 rows)

Accounts identified as protected (private) during fetching — can't retrieve their data.

| Column | Notes |
|---|---|
| account_id | |
| username | |
| reason | Why marked protected |
| discovered_at | |
| status | Current status |

---

### `account_note` (1 row)

Free-text notes on specific accounts (manual annotations not fitting elsewhere).

| Column | Notes |
|---|---|
| account_id | |
| note | The note text |
| updated_at | |

---

### `tweet_enrichment_cache` (49 rows)

Cached media and quote metadata for tweets fetched during enrichment.

| Column | Notes |
|---|---|
| tweet_id | |
| media_json | JSON array of media objects |
| quote_json | JSON for quoted tweet |
| full_text | Full text including quoted content |
| fetched_at | |

---

### `tweet_replies_cache` (0 rows)

Placeholder for caching reply threads. Not yet populated.

---

### `api_endpoint_costs` (11 rows)

Reference table: credits, yield, and signal value per API endpoint. Used for cost estimation in enrichment planning.

| Column | Notes |
|---|---|
| endpoint | API endpoint name |
| credits_per_call | Cost in API credits |
| typical_data_yield | How much data per call |
| signal_value | Qualitative signal value rating |
| notes | Free-text |

---

## 12. Key Relationships

### account_id joins

`account_id` is the universal account identifier. It's a string (Twitter's numeric ID as text). It links across:

```
tweets.account_id
likes.liker_account_id
retweets.account_id
profiles.account_id
account_following.account_id / following_account_id
account_followers.account_id / follower_account_id
community_account.account_id
community_membership.account_id
account_community_bits.account_id
account_band.account_id
account_engagement_agg.source_id / target_id
bio_embeddings.account_id
resolved_accounts.account_id
user_profile_cache.account_id
```

**Never join on username** — handles change. Always join on `account_id`. Use `resolved_accounts` to get current username for display.

---

### community_id joins

`community.id` (UUID) is the canonical community identifier. It links:

```
community_account.community_id
account_community_bits.community_id
community_alias.community_id
account_community_gold_label_set.community_id
community_snapshot_data (via JSON kind=community_account)
```

`community_run.run_id` + `community_membership.community_idx` is a different identifier used for **raw NMF output** — not the same as `community.id`. To link a run's component to a named community, join through `community.seeded_from_run` + `community.seeded_from_idx`.

---

### tweet_id joins

`tweet_id` links:

```
tweets.tweet_id (source of truth for archive tweets)
enriched_tweets.tweet_id (source of truth for API-fetched tweets)
tweet_tags.tweet_id → enriched_tweets
tweet_enrichment_cache.tweet_id
thread_context_cache.tweet_id
tweet_label_set.tweet_id
curation_split.tweet_id → tweets
chrome_audit_log.tweet_id
```

Note: `likes.tweet_id` may reference tweets NOT in `tweets` (liked from non-archived accounts).

---

### NMF run chain

```
community_run (run metadata)
  → community_membership (raw weights per account per component)
  → community_definition (top features per component)

community (named, colored, production)
  ← seeded_from_run + seeded_from_idx links back to community_run
  → community_account (production memberships)
```

---

### Labeling evidence chain

```
enriched_tweets (fetched tweets for a candidate account)
  → tweet_tags (human tags applied during labeling)
  → account_community_bits (rolled up: bits per account per community)
  → community_account (promoted to production via source='llm_ensemble' or manual)
```

---

### Propagation chain

```
community_account (seeds)
  → account_band (propagated to 298K accounts)
  → frontier_ranking (prioritized candidates for next enrichment round)
```

---

## 13. Source of Truth Map

| Question | Table |
|---|---|
| What did account X tweet? | `tweets` |
| What did account X like? | `likes` (filter on `liker_account_id`) |
| What is account X's current username? | `resolved_accounts` |
| What community does account X belong to? | `account_community_bits` (if populated), else `community_account` |
| What are all named communities? | `community` |
| What are the raw NMF weights for a run? | `community_membership` |
| What features define a community? | `community_definition` |
| Does account X follow account Y? | `account_following` |
| What band is account X in? | `account_band` |
| Has account X been manually verified? | `account_community_gold_label_set` |
| What tweets has account X been labeled on? | `tweet_label_set` + `tweet_label_prob` |
| What is the train/dev/test split for tweet X? | `curation_split` |
| What is the cost of API endpoint E? | `api_endpoint_costs` |
| Is account X a known TPOT member (holdout)? | `tpot_directory_holdout` |
| What is account X's bio embedding? | `bio_embeddings` |
| What are account X's topic weights? | `account_content_profile` |
| How much engagement does X send to Y? | `account_engagement_agg` |
