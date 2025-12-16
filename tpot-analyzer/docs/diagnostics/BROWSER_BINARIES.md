# Browser Binaries (Avoid “Chrome for Testing” Cache Bloat)

## Goal

Use a single, system-installed Chromium browser (e.g. Brave) for automation tools so they don’t keep downloading “Google Chrome for Testing.app” into cache directories.

On macOS, these cached `.app` bundles can show up in **System Settings → Default web browser**, even though they’re not in `/Applications`.

## Selenium (this repo)

### Configure once (recommended)

Set one of these env vars:

```bash
export TPOT_CHROME_BINARY="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
# or (more generic)
export CHROME_BIN="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
```

The enrichment CLI (`scripts/enrich_shadow_graph.py`) and Selenium worker (`src/shadow/selenium_worker.py`) will use these automatically.

### Configure per-run (alternative)

```bash
python3 -m scripts.enrich_shadow_graph --chrome-binary "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
```

## Puppeteer (general guidance)

This repo doesn’t use Puppeteer, but for other projects:

- Prefer `puppeteer-core` (so it **doesn’t** auto-download a bundled browser).
- Point it at your system browser:

```bash
export PUPPETEER_SKIP_DOWNLOAD=1
export PUPPETEER_EXECUTABLE_PATH="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
```

## Cleanup (manual, optional)

Once you’ve confirmed Selenium/Puppeteer are using your system browser, you can delete downloaded “Chrome for Testing” caches.

Common locations:

- Selenium Manager: `~/.cache/selenium/chrome/`
- Puppeteer: `~/.cache/puppeteer/`
- Playwright: `~/Library/Caches/ms-playwright/` (Playwright-managed; only delete if you intend to re-install browsers)

To inventory:

```bash
find "$HOME/.cache/selenium/chrome" "$HOME/.cache/puppeteer" "$HOME/Library/Caches/ms-playwright" \
  -maxdepth 10 -name "Google Chrome for Testing.app" -print
```

