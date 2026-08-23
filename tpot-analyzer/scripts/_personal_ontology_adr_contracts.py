"""Declarative ADR semantics protected by the personal-ontology docs verifier."""

from __future__ import annotations


ADR_SEMANTIC_CONTRACTS = (
    (
        "adr07",
        "ADR 007 records GRF and coverage limits",
        (
            "bounded, uncalibrated harmonic graph affinity",
            "heuristic graph uncertainty",
            "coverage is unknown",
            "compatible calibration record",
        ),
        "affinity, uncertainty, unknown coverage, and calibration",
    ),
    (
        "adr11",
        "ADR 011 records independent-affinity limits",
        (
            "independent account-by-community affinities",
            "registered development/calibration labels",
            "untouched terminal labels",
            "not a probability distribution",
        ),
        "per-task calibration and untouched terminal evaluation",
    ),
    (
        "adr12",
        "ADR 012 distinguishes producer score semantics",
        (
            "compositional factor shares",
            "bounded, uncalibrated harmonic graph affinity",
            "score availability, not evidence coverage",
            "snapshot generation, and as-of time",
        ),
        "NMF shares, GRF affinities, and compatible coverage",
    ),
    (
        "adr13",
        "ADR 013 limits probability-shaped color fields",
        (
            "compatibility names",
            "score availability is not evidence coverage",
            "heuristic rendering score",
            "registered calibration record",
        ),
        "legacy names, rendering score, and calibration gate",
    ),
)
