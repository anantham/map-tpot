"""Versioned Community Gold tables and indexes for schema version 3."""

COMMUNITY_GOLD_SCHEMA_VERSION = 3

VERSIONED_TABLES = """
DROP INDEX IF EXISTS idx_account_community_gold_active;

CREATE TABLE IF NOT EXISTS account_community_gold_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS personal_ontology_version (
    user_id TEXT NOT NULL,
    ontology_id TEXT NOT NULL,
    ontology_version INTEGER NOT NULL CHECK (ontology_version > 0),
    definition_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    supersedes_version INTEGER,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ontology_id, ontology_version)
);

CREATE TABLE IF NOT EXISTS personal_ontology_group (
    user_id TEXT NOT NULL,
    ontology_id TEXT NOT NULL,
    ontology_version INTEGER NOT NULL,
    community_id TEXT NOT NULL,
    boundary_definition TEXT NOT NULL,
    PRIMARY KEY (
        user_id, ontology_id, ontology_version, community_id
    ),
    FOREIGN KEY (user_id, ontology_id, ontology_version)
        REFERENCES personal_ontology_version(
            user_id, ontology_id, ontology_version
        ) ON DELETE RESTRICT,
    FOREIGN KEY (community_id)
        REFERENCES community(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS personal_ontology_task (
    user_id TEXT NOT NULL,
    ontology_id TEXT NOT NULL,
    ontology_version INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (
        target_type IN ('affiliation','competence','participation_interest')
    ),
    definition_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ontology_id, ontology_version, task_id),
    FOREIGN KEY (user_id, ontology_id, ontology_version)
        REFERENCES personal_ontology_version(
            user_id, ontology_id, ontology_version
        ) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_community_role_registry (
    role_registry_id TEXT NOT NULL PRIMARY KEY,
    registry_json TEXT NOT NULL,
    registry_digest TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_community_global_role (
    role_registry_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    assigned_role TEXT NOT NULL,
    role_json TEXT NOT NULL,
    role_hash TEXT NOT NULL,
    PRIMARY KEY (role_registry_id, account_id),
    FOREIGN KEY (role_registry_id)
        REFERENCES account_community_role_registry(role_registry_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_community_evaluation_frame (
    frame_id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    ontology_id TEXT NOT NULL,
    ontology_version INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_digest TEXT NOT NULL UNIQUE,
    evidence_snapshot_id TEXT NOT NULL,
    evidence_snapshot_hash TEXT NOT NULL,
    graph_manifest_hash TEXT NOT NULL,
    evidence_cutoff TEXT NOT NULL,
    role_registry_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id, ontology_id, ontology_version, task_id)
        REFERENCES personal_ontology_task(
            user_id, ontology_id, ontology_version, task_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (role_registry_id)
        REFERENCES account_community_role_registry(role_registry_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_community_evaluation_role (
    frame_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    stratum TEXT NOT NULL,
    assigned_role TEXT NOT NULL,
    assigned_probability REAL NOT NULL CHECK (
        assigned_probability > 0.0 AND assigned_probability <= 1.0
    ),
    terminal_test_probability REAL NOT NULL CHECK (
        terminal_test_probability > 0.0
        AND terminal_test_probability <= 1.0
    ),
    role_probabilities_json TEXT NOT NULL,
    PRIMARY KEY (frame_id, account_id),
    FOREIGN KEY (frame_id)
        REFERENCES account_community_evaluation_frame(frame_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_community_gold_head (
    frame_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    community_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    label_set_id INTEGER NOT NULL UNIQUE,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (frame_id, account_id, community_id, reviewer),
    FOREIGN KEY (frame_id)
        REFERENCES account_community_evaluation_frame(frame_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (community_id)
        REFERENCES community(id) ON DELETE RESTRICT,
    FOREIGN KEY (label_set_id)
        REFERENCES account_community_gold_label_set(id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_community_terminal_test_access (
    frame_id TEXT NOT NULL PRIMARY KEY,
    role_registry_id TEXT NOT NULL UNIQUE,
    accessed_by TEXT NOT NULL,
    access_receipt_json TEXT NOT NULL,
    access_receipt_hash TEXT NOT NULL,
    release_manifest_json TEXT NOT NULL,
    release_manifest_hash TEXT NOT NULL,
    access_envelope_hash TEXT NOT NULL,
    released_label_head_count INTEGER NOT NULL CHECK (
        typeof(released_label_head_count) = 'integer'
        AND released_label_head_count > 0
    ),
    accessed_at TEXT NOT NULL,
    FOREIGN KEY (frame_id)
        REFERENCES account_community_evaluation_frame(frame_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (role_registry_id)
        REFERENCES account_community_role_registry(role_registry_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS account_community_prediction (
    prediction_id TEXT NOT NULL PRIMARY KEY,
    frame_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    community_id TEXT NOT NULL,
    model_run_id TEXT NOT NULL,
    score REAL NOT NULL,
    score_semantics TEXT NOT NULL CHECK (
        score_semantics IN ('simplex','lift','affinity','calibrated_probability')
    ),
    calibration_record_hash TEXT,
    evidence_snapshot_id TEXT NOT NULL,
    evidence_snapshot_hash TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    predicted_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY (frame_id)
        REFERENCES account_community_evaluation_frame(frame_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (community_id)
        REFERENCES community(id) ON DELETE RESTRICT
);
"""

VERSIONED_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_account_community_gold_active_legacy
ON account_community_gold_label_set(account_id, community_id, reviewer)
WHERE is_active = 1 AND identity_status = 'legacy_unbound';

CREATE INDEX IF NOT EXISTS idx_account_community_gold_scoped_history
ON account_community_gold_label_set(
    study_frame_id, account_id, community_id, reviewer, id DESC
)
WHERE identity_status = 'scoped';

CREATE UNIQUE INDEX IF NOT EXISTS idx_global_role_one_registry_per_account
ON account_community_global_role(account_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_terminal_access_one_per_registry
ON account_community_terminal_test_access(role_registry_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_natural_generation_key
ON account_community_prediction(
    frame_id, account_id, community_id, model_run_id
);
"""
