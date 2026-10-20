# Map TPOT application

**[Documentation hub](docs/index.md)** ·
[Methods and lessons](docs/guides/DISCOVERY_METHODS.md) ·
[Roadmap](docs/ROADMAP.md)

Review helps you investigate accounts, inspect the evidence behind search results
and revise overlapping tags. It is the current discovery workflow, separate from
the [legacy community-map pipeline](docs/archive/legacy-community-map.md).

## Start with the workflow

1. Read [Mapping communities by example](docs/guides/DISCOVERY_METHODS.md) for the
   discovery loop, evaluation limits and lessons from unsuccessful approaches.
2. Follow the [Review guide](docs/guides/DISCOVERY_REVIEW.md) for the tagging and
   evidence-inspection workflow, including private curator authentication.
3. Use the [Quickstart](docs/guides/QUICKSTART.md) for dependencies and the
   [Playbook](docs/PLAYBOOK.md) for the API/explorer workflow.
4. Read the [data boundary](docs/guides/DATA_BOUNDARY.md) before configuring real
   inputs. No private dataset is bundled or fetched automatically by these docs.

The CI baseline is Python 3.11 and Node 22. A fresh clone can run synthetic tests;
real discovery needs your own permitted source data and matching configuration.
Source unavailability should remain visible, not be replaced with sample people.

## Current capabilities

- Search saved profiles, eligible posts, cached websites and work on exact accounts.
- Open the matched passage, original page/post or retained source pointer.
- Add independent IN/NOT IN tags, optional notes and reversible corrections.
- Inspect directed follow/reply/repost paths and source coverage.
- Compare graph methods with the [hide-and-recover experiment](docs/diagnostics/tag-seed-recovery.md).
- View contextual contact clues without treating them as verified ownership or consent.

Rank scores are not membership probabilities. Cross-platform links do not
automatically merge people, and saved work associations do not establish competence.

## Code and documentation layout

| Folder | Responsibility |
| --- | --- |
| [src/api](src/api/) | Flask routes, authentication and response contracts |
| [src/data](src/data/) | Source readers, qualified joins, derived evidence and tags |
| [src/graph](src/graph/) | Graph scoring, paths and recovery experiments |
| [graph-explorer](graph-explorer/) | Private Review and analysis interface |
| [public-site](public-site/) | Older public community visualization |
| [scripts](scripts/) | Explicit import, experiment and verification entrypoints |
| [tests](tests/) | Invented fixtures and behavioral checks |
| [docs](docs/index.md) | Guides, methods, contracts, roadmap and historical material |

## Verification

Follow [Test mode](docs/guides/TEST_MODE.md) and the
[testing methodology](docs/TESTING_METHODOLOGY.md). On an existing private install,
isolate persistence and lease roots before importing the application for tests.
Live Supabase and browser integration tests need separate configuration.

The read-only documentation and tracked-data checks can be run from this folder:

```sh
python3 scripts/verify_docs_hygiene.py
python3 scripts/verify_shareable_checkout.py
```

These do not certify all content, Git history or historical research conclusions.
See the [public worklog](docs/WORKLOG.md) for the tested publication checkpoint.

## Historical material

The previous long README, including NMF communities, old pipeline commands and
historical counts, is preserved in [the archive](docs/archive/legacy-community-map.md).
It is not the current setup guide. The [docs hub](docs/index.md) separates current
guidance from plans and historical analysis.

## Reuse

A project-wide license remains unselected. No license is added by this documentation cleanup.
