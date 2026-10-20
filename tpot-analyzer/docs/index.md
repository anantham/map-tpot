# Map TPOT documentation

## Start here

- [Methods and lessons](guides/DISCOVERY_METHODS.md): the learnable discovery loop,
  negative experiments and limits; invented examples, no contact directory.
- [Review setup](guides/DISCOVERY_REVIEW.md): private Review versus the older map.
- [Data boundary](guides/DATA_BOUNDARY.md): what a clone contains and cannot reproduce.
- [Source inventory contract](DATA_INVENTORY.md): count observations without implying completeness.
- [Roadmap](ROADMAP.md), [public worklog](WORKLOG.md), [experiment summary](EXPERIMENT_LOG.md).
- [Graph hide-and-recover](diagnostics/tag-seed-recovery.md): fixed methods and falsifiers.

## Build and verify

- [Playbook](PLAYBOOK.md)
- [Quickstart](guides/QUICKSTART.md)
- [Test mode](guides/TEST_MODE.md)
- [Testing methodology](TESTING_METHODOLOGY.md)
- [Application layout](../README.md#code-and-documentation-layout)
- [Engineering conventions](CONVENTIONS.md)
- [Architecture decisions](adr/): source-backed relationships, joined search,
  historical observations and contextual contact clues.

## Documentation folders

| Location | What belongs here |
| --- | --- |
| [guides/](guides/) | Methods, user workflows, setup and operating guidance |
| [adr/](adr/) | Architecture decisions and source/identity contracts |
| [reference/](reference/) | Schemas, environment variables and technical reference |
| [modules/](modules/INDEX.md) | Source-module responsibilities and entrypoints |
| [product/](product/) | User feedback and UI behavior specifications |
| [experiments/](experiments/) | Research designs and experimental methods, not live status |
| [diagnostics/](diagnostics/) | Focused investigations and algorithm diagnostics |
| [plans/](plans/) | Dated proposals and implementation plans, not proof of delivery |
| [archive/](archive/) | Superseded guidance retained for historical context |

The docs root holds this hub, the roadmap, worklog, experiment summary and
cross-cutting conventions. New topic-specific material belongs in a folder above.
Some older root-level notes remain at their original paths for compatibility;
they are not automatically current guidance.

## Historical / Planning Notes

`docs/README.md` was added on 20 October 2026 as the GitHub directory landing
page. This index remains the maintained navigation hub.

- [Previous community-map README](archive/legacy-community-map.md), preserved on
  20 October 2026 and superseded by the [current application README](../README.md).
- [Older NMF validation](NMF_V2_VALIDATION.md) and
  [propagation analysis](PROPAGATION_ANALYSIS.md) describe historical artifacts,
  not current membership calibration or discovery precision.

Older docs under `archive/`, `tasks/`, `plans/` and early ADRs describe earlier
approaches and are not current deployment or data-coverage statements. This
publication replaces private operational ledgers with curated summaries; it does
not bundle the underlying private experiment inputs. Prefer the current methods,
roadmap and source contracts when an older note conflicts.
