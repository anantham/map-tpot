# Graph Explorer for TPOT Analyzer

Interactive frontend for visualizing the TPOT community graph. Built with Vite + React + `react-force-graph-2d`.

## Prerequisites

- Node.js 18+
- Access to the `tpot-analyzer` Python project and its virtualenv

## Setup

```bash
cd tpot-analyzer/graph-explorer
npm install
```

## Refresh data from the CLI

A helper script regenerates `analysis_output.json` inside `public/` using the Python analyzer. By default it runs in mutual-only mode with the "Adi's Seeds" preset.

```bash
npm run refresh-data
```

Options:

```
# Use a different preset (from DEFAULT_PRESETS in GraphExplorer.jsx)
npm run refresh-data -- --preset "Adi's Seeds"

# Supply custom seeds (handles or account_ids)
npm run refresh-data -- --seeds nosilverv DefenderOfBasic 1464483769222680582

# Disable mutual-only filter and change min followers
npm run refresh-data -- --no-mutual --min-followers 2
```

The script invokes `python -m scripts.analyze_graph` from the project root and places the JSON output into `graph-explorer/public/analysis_output.json`.

## Run the dev server

```bash
npm run dev
```

Open the URL shown (default `http://localhost:5173`). Use the left pane to tweak metrics, layout, and seeds. The “Download CSV” button exports the current ranking; “Refresh Data” attempts to call the optional refresh endpoint (see below).

## Optional: auto-refresh endpoint

If you run a local backend that exposes `POST /__refresh` (e.g. via an Express proxy or Flask handler that calls the refresh script), the “Refresh Data” button will trigger it and refetch the JSON. Otherwise the button simply logs a warning.

## Build preview

```bash
npm run build
npm run preview
```

## Linting

```bash
npm run lint
```

---

For additional presets, update the `DEFAULT_PRESETS` object in `src/GraphExplorer.jsx` or wire it to a shared JSON file.
