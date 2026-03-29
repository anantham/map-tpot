# twitterapi.io Endpoint Map for Labeling Pipeline

Base URL: `https://api.twitterapi.io/twitter/`
Auth: `X-API-Key` header
Full docs index: `https://docs.twitterapi.io/llms.txt`

## Cost-Conscious Usage

These are paid API calls. Use sparingly — only with user approval.
Syndication API (free, no auth) should be preferred for single-tweet data.

**Budget per non-archive account: ~25 calls**

### Pricing (2026-03-28)

Plan: $20 for 2,000,000 credits.

| Endpoint | Credits/page | Results/page | Cost/page | Notes |
|----------|-------------|-------------|-----------|-------|
| `user/followings` | ~3,000 | ~200 | $0.03 | Varies: 2745-3000/page, 495 for final partial page |
| `user/info` | ~1,000 | 1 | $0.01 | Single profile |
| `user/batch_info_by_ids` | ~1,000 | up to 100 | $0.01 | Bulk profiles — best value |
| `user/last_tweets` | ~3,000 | ~20 | $0.03 | Per page |
| `tweet/thread_context` | ~3,000 | varies | $0.03 | Full thread |

**Actual cost examples (measured 2026-03-28):**
- @ch402 (183 following): 1 page, 3,000 credits = $0.03
- @natfriedman (832 following): 6 pages, 15,240 credits = $0.15
- 188 zero-outbound accounts: estimated ~1.7M credits = ~$17

## Tested Endpoints (2026-03-22)

### Working

| Endpoint | Method | Params | Returns | Calls/account | Notes |
|----------|--------|--------|---------|---------------|-------|
| `user/info` | GET | userName | Profile, follower/following count, bio, location, isAutomated | 1 | Also returns pinnedTweetIds, profile_bio with URL entities |
| `user/batch_info_by_ids` | GET | userIds (comma-sep, max 100) | Same as user/info but batched | 1 per 100 | Key: response has `users` array |
| `user/last_tweets` | GET | userName, pageSize, cursor | Tweets (nested in data.tweets) | 3-5 | Filter RTs client-side |
| `user/followings` | GET | userName, pageSize, cursor | Following list | 10 per 1890 | Key: `followings` not `data` |
| `user/followers` | GET | userName, pageSize, cursor | Follower list | 1-2 | First 200 usually enough |
| `tweet/replies` | GET | tweetId | Reply tweets with author info | 1/tweet | Replaces Chrome for engagement |
| `tweet/retweeters` | GET | tweetId, cursor | Users who retweeted, ~100/page | 1/tweet | |
| `user/mentions` | GET | userName | Tweets mentioning user | 1 | Empty for small accounts |
| `tweet/advanced_search` | GET | query, queryType | Tweets matching query | 1 | queryType: "Latest" or "Top" |

### Available (from official docs, 2026-03-24)

| Endpoint | Method | Params | Returns | Notes |
|----------|--------|--------|---------|-------|
| `user/tweet_timeline` | GET | userId, includeReplies, includeParentTweet, cursor | Tweets in profile order, 20/page | Use userId (not userName) |
| `user_about` | GET | userName | Extended profile: account_based_in, affiliate_username, username_changes | Verified location + org badges |
| `user/check_follow` | GET | sourceUserName, targetUserName | Boolean follow relationship | Per-pair check, no pagination |
| `tweet/quotes` | GET | tweetId, sinceTime, untilTime, includeReplies, cursor | Quote tweets, 20/page | URL is `/tweet/quotes` (not `/tweet/quotations`) |
| `tweet/thread_context` | GET | tweetId, cursor | Full thread: ancestors + descendants | Input any tweet in thread, get full context |
| `user/search` | GET | query | Users matching keyword | |
| `user/verified_followers` | GET | userId, cursor | Blue-verified followers | |
| `tweet/replies_v2` | GET | tweetId, cursor | Replies (v2 format) | |
| List endpoints | GET | various | List timeline, followers, members | `/list/tweet_timeline`, `/list/followers`, `/list/members` |
| Community endpoints | GET | various | Community info, members, tweets | `/community/info`, `/community/members`, `/community/tweets` |

### Key Response Fields (user/info)

```json
{
  "data": {
    "userName": "...", "id": "...", "name": "...",
    "description": "...",           // bio text
    "location": "...",              // self-reported location
    "followers": 123,               // follower count
    "following": 123,               // following count
    "statusesCount": 123,           // total tweets
    "favouritesCount": 123,         // total likes given
    "isBlueVerified": true,
    "isAutomated": true,            // bot flag
    "automatedBy": "...",           // who runs the bot
    "pinnedTweetIds": ["..."],
    "createdAt": "2006-07-16T...",
    "profile_bio": {                // bio with resolved URLs
      "description": "...",
      "entities": { "description": { "urls": [...] }, "url": { "urls": [...] } }
    }
  }
}
```

### Key Response Fields (user_about)

```json
{
  "data": {
    "id": "...", "userName": "...",
    "about_profile": {
      "account_based_in": "United States",   // verified location (X determines this)
      "location_accurate": true,
      "affiliate_username": "OpenAI",         // org affiliation
      "username_changes": { "count": "2" }    // handle change history
    },
    "affiliates_highlighted_label": {         // org badge
      "label": { "description": "OpenAI", "badge": { "url": "..." } }
    }
  }
}
```

### Not Working

| Endpoint | Status | Notes |
|----------|--------|-------|
| `tweet/multi` (batch by IDs) | 404 | May need different param format |

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

## Known Issues (2026-03-24)

### `user/followings` silent rate limit
After ~120 calls in a session, the endpoint returns HTTP 200 with `{"data": []}` instead of a 429 error. The `user/followers` endpoint continues working normally. This appears to be a daily quota — reset time unknown.

**Workaround:** Use Chrome scraping (`x.com/{handle}/following` + auto-scroll + extract handles) for followings. Chrome scraping gets ~25-40 handles per account (limited by X's scroll rendering).

**Impact:** Batch 1 fetched 22,338 edges before the limit hit. All subsequent followings calls returned 0.
