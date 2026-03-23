# twitterapi.io Endpoint Map for Labeling Pipeline

Base URL: `https://api.twitterapi.io/twitter/`
Auth: `X-API-Key` header

## Cost-Conscious Usage

These are paid API calls. Use sparingly — only with user approval.
Syndication API (free, no auth) should be preferred for single-tweet data.

**Budget per non-archive account: ~25 calls**

## Tested Endpoints (2026-03-22)

### Working

| Endpoint | Method | Params | Returns | Calls/account | Notes |
|----------|--------|--------|---------|---------------|-------|
| `user/info` | GET | userName | Profile, follower/following count, bio | 1 | |
| `user/last_tweets` | GET | userName, pageSize, cursor | Tweets (nested in data.tweets) | 3-5 | Filter RTs client-side |
| `user/followings` | GET | userName, pageSize, cursor | Following list | 10 per 1890 | Key for community signal |
| `user/followers` | GET | userName, pageSize, cursor | Follower list | 1-2 | First 200 usually enough |
| `tweet/replies` | GET | tweetId | Reply tweets with author info | 1/tweet | Replaces Chrome for engagement |
| `tweet/retweeters` | GET | tweetId | Users who retweeted | 1/tweet | |
| `user/mentions` | GET | userName | Tweets mentioning user | 1 | Empty for small accounts |
| `tweet/advanced_search` | GET | query, queryType | Tweets matching query | 1 | queryType: "Latest" or "Top" |

### Not Working / Untested

| Endpoint | Status | Notes |
|----------|--------|-------|
| `tweet/multi` (batch by IDs) | 404 | May need different param format |
| `tweet/quotations` | 404 | May need different URL |
| `user/verified_followers` | Untested | |
| `user/profile_about` | Untested | |
| `tweet/replies_v2` | Untested | |

## Response Structures

### user/last_tweets
```json
{
  "status": "success",
  "data": {
    "pin_tweet": {...},
    "tweets": [
      {
        "id": "123...",
        "text": "...",
        "createdAt": "...",
        "likeCount": 5,
        "retweetCount": 2,
        "author": {
          "id": "456...",
          "userName": "bhi5hmaraj",
          "name": "Bhishmaraj S"
        },
        "quoted_tweet": {...} or null,
        "mediaDetails": [...]
      }
    ]
  },
  "has_next_page": true,
  "next_cursor": "..."
}
```

### user/followings
```json
{
  "followings": [
    {"userName": "...", "id": "...", "name": "...", ...}
  ],
  "has_next_page": true,
  "next_cursor": "..."
}
```

### tweet/replies
```json
{
  "tweets": [
    {"id": "...", "text": "...", "author": {"userName": "..."}, ...}
  ],
  "has_next_page": false
}
```

## Pipeline: Non-Archive Account Enrichment

```
1. user/info                    → profile, stats             (1 call)
2. user/last_tweets × 3-5      → 60-100 tweets              (3-5 calls)
3. user/followings × N          → full following list         (N calls)
4. user/followers × 1-2         → top 200 followers          (1-2 calls)
5. tweet/replies × 10           → engagement on top tweets   (10 calls)
                                                    TOTAL: ~20-25 calls

Then:
6. Syndication API              → images, quotes             (FREE)
7. Insert into SQLite           → tweets + profile tables
8. AI labeling                  → proposed labels
9. Human review                 → approve/correct
```

## Comparison: Archive vs Non-Archive

| Data | Archive account | Non-archive (API) |
|------|----------------|-------------------|
| Tweets | All (thousands) | Last ~100 (API limit) |
| Likes given | 17.5M total | NOT available via API |
| Followers | Full list | Full list (paginated) |
| Following | Full list | Full list (paginated) |
| Reply relationships | All in DB | Per-tweet API call |
| Retweet relationships | All in DB | Per-tweet API call |
| Images | Syndication (free) | Syndication (free) |
| Quote tweets | Syndication (free) | Syndication (free) |
| Cost | Free (data in SQLite) | ~25 API calls/account |

The biggest gap for non-archive accounts: **likes given** (who they like).
This is the strongest engagement signal and is only available from the archive.
