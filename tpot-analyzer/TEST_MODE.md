# Test Mode Usage Guide

## Overview

The API server now supports a **test mode** that uses a small subset of 100 nodes instead of the full database. This allows for fast iteration during UI development.

## Performance Comparison

| Mode | Nodes | Edges | Response Time |
|------|-------|-------|---------------|
| **Production** | 3,931 | 9,516 | ~33 seconds |
| **Test** | 100 | 269 | ~0.4 seconds |

## Running in Test Mode

### Option 1: Using the `--test` flag (recommended)

```bash
.venv/bin/python3 scripts/api_server.py --test
```

### Option 2: Using environment variable

```bash
TEST_MODE=1 .venv/bin/python3 scripts/api_server.py
```

## Running in Production Mode

Just run the server normally (without flags):

```bash
.venv/bin/python3 scripts/api_server.py
```

## Creating Custom Test Subsets

You can create a test subset with a different number of nodes:

```bash
# Create a 200-node test subset
.venv/bin/python3 scripts/create_test_subset.py 200

# Create a 50-node test subset
.venv/bin/python3 scripts/create_test_subset.py 50
```

The subset will be saved to `data/test_subset.json` and automatically loaded when running in test mode.

## Test Subset Details

- **Seed accounts**: Starts with Adi's 18 seed accounts
- **Expansion**: Uses BFS (Breadth-First Search) to find connected nodes
- **Result**: A connected subgraph with exactly N nodes + their edges

## Workflow Recommendation

1. **During UI development**: Use test mode (`--test`) for fast iteration
2. **Before committing**: Test with production mode to ensure it works with the full dataset
3. **Demo/presentation**: Use test mode for quick loading

## Logs

When running in test mode, you'll see:

```
2025-10-07 11:28:39,021 [INFO] __main__: Test mode: ENABLED
2025-10-07 11:28:39,021 [INFO] __main__: Using test subset from: /path/to/data/test_subset.json
2025-10-07 11:29:10,226 [INFO] __main__: Loaded 100 accounts and 269 edges from test subset
```

When running in production mode:

```
2025-10-07 11:28:39,021 [INFO] __main__: Test mode: DISABLED
2025-10-07 11:28:39,037 [INFO] __main__: Using database at: /path/to/shadow_cache.db
2025-10-07 11:28:44,127 [INFO] __main__: Fetched 3931 accounts and 9516 edges
```
