"""SQLite integrity triggers dedicated to immutable study predictions."""

PREDICTION_TRIGGERS = """
CREATE TRIGGER prevent_scoped_prediction_insert_after_release
BEFORE INSERT ON account_community_prediction
WHEN EXISTS (
    SELECT 1
    FROM account_community_evaluation_frame frame
    JOIN account_community_terminal_test_access access
      ON access.role_registry_id = frame.role_registry_id
    WHERE frame.frame_id = NEW.frame_id
)
BEGIN
    SELECT RAISE(ABORT, 'evaluation generation is sealed after terminal release');
END;

CREATE TRIGGER validate_scoped_prediction_binding
BEFORE INSERT ON account_community_prediction
WHEN NOT EXISTS (
    SELECT 1
    FROM account_community_evaluation_frame frame
    WHERE frame.frame_id = NEW.frame_id
      AND frame.evidence_snapshot_id = NEW.evidence_snapshot_id
      AND frame.evidence_snapshot_hash = NEW.evidence_snapshot_hash
      AND EXISTS (
          SELECT 1
          FROM personal_ontology_group ontology_group
          WHERE ontology_group.user_id = frame.user_id
            AND ontology_group.ontology_id = frame.ontology_id
            AND ontology_group.ontology_version = frame.ontology_version
            AND ontology_group.community_id = NEW.community_id
      )
      AND (
          EXISTS (
              SELECT 1
              FROM account_community_evaluation_role role
              WHERE role.frame_id = frame.frame_id
                AND role.account_id = NEW.account_id
          )
          OR EXISTS (
              SELECT 1
              FROM json_each(frame.manifest_json, '$.fixedTrainingIds') item
              WHERE CAST(item.value AS TEXT) = NEW.account_id
          )
          OR EXISTS (
              SELECT 1
              FROM json_each(frame.manifest_json, '$.fixedChallengeIds') item
              WHERE CAST(item.value AS TEXT) = NEW.account_id
          )
      )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'prediction must match its frame U0, ontology, and evidence generation'
    );
END;

CREATE TRIGGER validate_scoped_prediction_score
BEFORE INSERT ON account_community_prediction
WHEN (
    NEW.score_semantics = 'simplex'
    AND (NEW.score < 0.0 OR NEW.score > 1.0)
) OR (
    NEW.score_semantics = 'lift' AND NEW.score < 0.0
)
BEGIN
    SELECT RAISE(ABORT, 'prediction score is outside its semantic domain');
END;

CREATE TRIGGER prevent_unregistered_probability_insert
BEFORE INSERT ON account_community_prediction
WHEN NEW.score_semantics = 'calibrated_probability'
BEGIN
    SELECT RAISE(
        ABORT,
        'calibrated_probability requires a registered calibration record'
    );
END;

CREATE TRIGGER prevent_scoped_prediction_update
BEFORE UPDATE ON account_community_prediction
BEGIN
    SELECT RAISE(ABORT, 'immutable prediction record cannot be updated');
END;

CREATE TRIGGER prevent_scoped_prediction_delete
BEFORE DELETE ON account_community_prediction
BEGIN
    SELECT RAISE(ABORT, 'immutable prediction record cannot be deleted');
END;
"""
