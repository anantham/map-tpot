# Map TPOT

Find potential collaborators and overlapping communities through inspectable
public evidence and your own examples. The private Review workspace joins
profiles, posts, websites, saved work and typed network paths, then lets you
revise independent tags while reading the sources.

## Documentation

**[Open the documentation hub](tpot-analyzer/docs/index.md)**

| You want to | Start here |
| --- | --- |
| Understand the approach and what failed | [Methods and lessons](tpot-analyzer/docs/guides/DISCOVERY_METHODS.md) |
| Set up or explore Review | [Application README](tpot-analyzer/README.md) |
| Find architecture, data contracts and developer guides | [Documentation hub](tpot-analyzer/docs/index.md) |
| See implemented work and next experiments | [Roadmap](tpot-analyzer/docs/ROADMAP.md) |
| Understand what stays private | [Data boundary](tpot-analyzer/docs/guides/DATA_BOUNDARY.md) |
| Understand the older NMF and propagation map | [Legacy README archive](tpot-analyzer/docs/archive/legacy-community-map.md) |

## Repository layout

```text
README.md                         Start here
.github/workflows/                CI checks
tpot-analyzer/                    Application and research tools
  README.md                       Setup and current capabilities
  docs/                           Methods, guides, decisions and history
  src/                            API, data readers and graph methods
  graph-explorer/                 Private Review and analysis UI
  public-site/                    Legacy public visualization
  scripts/                        Import, analysis and verification commands
  tests/                          Synthetic and integration tests
  data/                           Ignored local inputs and derived stores
```

There is one documentation tree: `tpot-analyzer/docs/`. Its
[folder guide](tpot-analyzer/docs/index.md#documentation-folders) explains where
to find and add material. Application and data paths stay stable.

## Scope and privacy

A clone contains code, documentation and invented test fixtures, not private
profiles, contact lists, tags or the research corpus. Historical map percentages
are not calibrated membership probabilities. Links and contact clues are not
verified identity, competence or permission to contact someone.

This publication branch is separate from the older default `main` until merged.
See the [data boundary](tpot-analyzer/docs/guides/DATA_BOUNDARY.md) for the limits
of checkout cleanup and existing public Git history.

## Reuse

Read and learn from the methods. A project-wide reuse license has not yet been
selected; this publication does not add one.
