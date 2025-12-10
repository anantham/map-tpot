# Security Guidelines

This document covers security considerations for developing and operating map-tpot.

---

## Secrets Management

### What Counts as a Secret

| Secret | Location | Purpose |
|--------|----------|---------|
| `SUPABASE_KEY` | `.env` | Community Archive access |
| `X_BEARER_TOKEN` | `.env` or CLI | X API authentication |
| `OPENROUTER_API_KEY` | `.env` | Grok-probe LLM access |
| Cookie files | `secrets/*.pkl` | Twitter session auth |

### Storage Best Practices

**DO:**
```bash
# Store secrets in .env (gitignored)
echo "SUPABASE_KEY=your_key" >> .env

# Store cookies in secrets/ directory (gitignored)
python -m scripts.setup_cookies --output secrets/twitter_cookies.pkl

# Use environment variables for CLI
X_BEARER_TOKEN=xxx python -m scripts.enrich_shadow_graph --enable-api-fallback
```

**DON'T:**
```bash
# ❌ Never commit secrets
git add .env
git add secrets/twitter_cookies.pkl

# ❌ Never hardcode in source
BEARER_TOKEN = "xxxxx"  # In Python file

# ❌ Never paste in issues/PRs
"My token is sk-or-xxxx"
```

### .gitignore Verification

Ensure these patterns are in `.gitignore`:
```
.env
.env.*
secrets/
*.pkl
twitter_cookies*.pkl
```

---

## Cookie Security

### What Cookies Contain

Twitter cookie files (`secrets/twitter_cookies.pkl`) contain:
- Session tokens (`auth_token`, `ct0`)
- Account identifiers
- Expiration timestamps

**Risk:** Anyone with these cookies can impersonate your Twitter session.

### Cookie Best Practices

1. **Never share cookie files** — They're equivalent to passwords
2. **Use dedicated accounts** — Don't use your main Twitter account
3. **Rotate regularly** — Re-capture cookies monthly
4. **Delete when done** — Remove cookie files after enrichment runs
5. **Label clearly** — Use `twitter_cookies_<purpose>_<date>.pkl`

### Cookie Capture Process

```bash
# Interactive capture (opens browser for manual login)
python -m scripts.setup_cookies --output secrets/twitter_cookies_enrichment_2024-12.pkl

# Browser stays open for you to log in
# Press Enter after login completes
# Cookies saved to pickle file
```

---

## API Token Security

### X API Bearer Tokens

If using `--enable-api-fallback`:

1. **Use app-only tokens** — Not user tokens when possible
2. **Limit permissions** — Request only needed scopes
3. **Monitor usage** — Check X Developer Portal for unexpected activity
4. **Rotate on suspicion** — Regenerate if potentially exposed

### Supabase Anon Key

The Community Archive anon key is:
- **Read-only** — Cannot modify archive data
- **Public** — Designed for client-side use
- **Rate-limited** — Supabase enforces limits

Still, don't commit it to public repos to avoid abuse.

---

## Safe Scraping Practices

### Rate Limiting

Twitter actively detects and blocks automated access:

| Behavior | Risk Level | Mitigation |
|----------|------------|------------|
| Rapid requests | High | Use delays (5-40s between actions) |
| Consistent timing | Medium | Add random jitter |
| Many accounts/session | High | Limit to 50-100 per session |
| Headless browser | Medium | Use visible browser when possible |

### Recommended Settings

```bash
# Conservative (slow but safe)
python -m scripts.enrich_shadow_graph \
  --delay-min 10 \
  --delay-max 40 \
  --max-scrolls 10

# Fast (higher detection risk)
python -m scripts.enrich_shadow_graph \
  --delay-min 2 \
  --delay-max 5 \
  --max-scrolls 30  # ⚠️ Use with caution
```

### If Blocked

1. **Stop immediately** — Don't retry aggressively
2. **Wait hours/days** — Twitter blocks are usually temporary
3. **Use different cookies** — Switch to another account session
4. **Reduce activity** — Lower scraping volume

---

## Data Privacy

### What Data is Collected

| Data Type | Source | Sensitivity |
|-----------|--------|-------------|
| Public profiles | Twitter | Low (public info) |
| Follow relationships | Twitter | Medium (social graph) |
| Tweets/likes | Community Archive | Medium (opted-in) |
| Scraped bios | Twitter | Medium (personal info) |

### Data Handling

1. **Don't redistribute raw data** — Especially shadow-scraped data
2. **Aggregate when sharing** — Use statistics, not individual records
3. **Respect opt-outs** — If someone asks to be removed, comply
4. **Delete on request** — Be prepared to purge individual data

### SQLite Cache

The `data/cache.db` file contains:
- Mirrored Community Archive data
- Shadow account/edge data
- Scrape history with timestamps

**Treat as sensitive** — Don't share or commit.

---

## Selenium Security

### Browser Profile Risks

Selenium can access:
- All browser cookies
- Saved passwords (if using existing profile)
- Browser history
- Extensions

### Mitigation

1. **Use fresh profiles** — Don't reuse personal browser profiles
2. **Sandbox when possible** — Run in VM or container
3. **Review HTML snapshots** — Check `logs/*.html` doesn't contain sensitive info
4. **Clear after use** — Delete browser profile directories

---

## Incident Response

### If Secrets Are Exposed

1. **Revoke immediately:**
   - Supabase: Regenerate anon key in dashboard
   - X API: Regenerate bearer token
   - OpenRouter: Regenerate API key
   - Cookies: Log out of Twitter session

2. **Audit usage:**
   - Check API dashboards for unusual activity
   - Review git history for exposure extent

3. **Notify if needed:**
   - If user data may be affected
   - If rate limits were exceeded on shared resources

### If Account Is Blocked

1. **Don't panic** — Temporary blocks are common
2. **Document** — Note what actions preceded the block
3. **Wait** — Usually resolves in 24-72 hours
4. **Adjust** — Increase delays for future runs

---

## Security Checklist

Before committing:
- [ ] No secrets in code or config files
- [ ] `.env` and `secrets/` in `.gitignore`
- [ ] No cookie files staged
- [ ] No API keys in logs or output

Before running enrichment:
- [ ] Using dedicated/alt account
- [ ] Cookies stored in `secrets/` directory
- [ ] Reasonable delay settings
- [ ] Prepared to stop if issues arise

Before sharing data:
- [ ] Aggregated, not raw records
- [ ] No PII beyond public profiles
- [ ] Provenance documented

---

## Reporting Security Issues

If you discover a security vulnerability:

1. **Don't open public issue** — Contains sensitive details
2. **Contact maintainer directly** — Via private channel
3. **Provide details:** — What, how, impact
4. **Allow time to fix** — Before public disclosure

---

*Security is everyone's responsibility. When in doubt, ask.*
