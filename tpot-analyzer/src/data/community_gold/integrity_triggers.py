"""SQLite triggers that make scoped scientific records fail closed."""

from .ontology_frame_triggers import ONTOLOGY_FRAME_TRIGGERS
from .prediction_triggers import PREDICTION_TRIGGERS

_CORE_INTEGRITY_TRIGGERS = """
CREATE TRIGGER prevent_scoped_gold_update
BEFORE UPDATE ON account_community_gold_label_set
WHEN OLD.identity_status = 'scoped' OR NEW.identity_status = 'scoped'
BEGIN
    SELECT RAISE(ABORT, 'scoped gold judgments are immutable; append a correction');
END;

CREATE TRIGGER prevent_scoped_gold_delete
BEFORE DELETE ON account_community_gold_label_set
WHEN OLD.identity_status = 'scoped'
BEGIN
    SELECT RAISE(ABORT, 'scoped gold judgments are immutable');
END;

CREATE TRIGGER prevent_scoped_gold_insert_after_release
BEFORE INSERT ON account_community_gold_label_set
WHEN NEW.identity_status = 'scoped' AND EXISTS (
    SELECT 1
    FROM account_community_evaluation_frame frame
    JOIN account_community_terminal_test_access access
      ON access.role_registry_id = frame.role_registry_id
    WHERE frame.frame_id = NEW.study_frame_id
)
BEGIN
    SELECT RAISE(ABORT, 'evaluation generation is sealed after terminal release');
END;

CREATE TRIGGER validate_scoped_gold_lineage_insert
BEFORE INSERT ON account_community_gold_label_set
WHEN NEW.identity_status = 'scoped' AND (
    (
        NEW.supersedes_label_set_id IS NULL
        AND EXISTS (
            SELECT 1 FROM account_community_gold_label_set prior
            WHERE prior.identity_status = 'scoped'
              AND prior.study_frame_id = NEW.study_frame_id
              AND prior.account_id = NEW.account_id
              AND prior.community_id = NEW.community_id
              AND prior.reviewer = NEW.reviewer
        )
    )
    OR (
        NEW.supersedes_label_set_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM account_community_gold_head head
            JOIN account_community_gold_label_set prior
              ON prior.id = head.label_set_id
            WHERE head.frame_id = NEW.study_frame_id
              AND head.account_id = NEW.account_id
              AND head.community_id = NEW.community_id
              AND head.reviewer = NEW.reviewer
              AND head.label_set_id = NEW.supersedes_label_set_id
              AND prior.identity_status = 'scoped'
              AND prior.study_frame_id = NEW.study_frame_id
              AND prior.account_id = NEW.account_id
              AND prior.community_id = NEW.community_id
              AND prior.reviewer = NEW.reviewer
        )
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'scoped judgment must extend the current head for the same identity'
    );
END;

CREATE TRIGGER validate_scoped_gold_head_insert
BEFORE INSERT ON account_community_gold_head
WHEN NOT EXISTS (
    SELECT 1 FROM account_community_gold_label_set ls
    WHERE ls.id = NEW.label_set_id
      AND ls.identity_status = 'scoped'
      AND ls.study_frame_id = NEW.frame_id
      AND ls.account_id = NEW.account_id
      AND ls.community_id = NEW.community_id
      AND ls.reviewer = NEW.reviewer
)
BEGIN
    SELECT RAISE(ABORT, 'scoped gold head does not match its label identity');
END;

CREATE TRIGGER validate_scoped_gold_head_update
BEFORE UPDATE ON account_community_gold_head
WHEN NEW.frame_id <> OLD.frame_id
  OR NEW.account_id <> OLD.account_id
  OR NEW.community_id <> OLD.community_id
  OR NEW.reviewer <> OLD.reviewer
  OR NOT EXISTS (
    SELECT 1 FROM account_community_gold_label_set ls
    WHERE ls.id = NEW.label_set_id
      AND ls.identity_status = 'scoped'
      AND ls.study_frame_id = NEW.frame_id
      AND ls.account_id = NEW.account_id
      AND ls.community_id = NEW.community_id
      AND ls.reviewer = NEW.reviewer
      AND ls.supersedes_label_set_id = OLD.label_set_id
)
BEGIN
    SELECT RAISE(
        ABORT,
        'scoped gold head must advance to a direct superseding judgment'
    );
END;

CREATE TRIGGER prevent_scoped_head_insert_after_release
BEFORE INSERT ON account_community_gold_head
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

CREATE TRIGGER prevent_scoped_head_update_after_release
BEFORE UPDATE ON account_community_gold_head
WHEN EXISTS (
    SELECT 1
    FROM account_community_evaluation_frame frame
    JOIN account_community_terminal_test_access access
      ON access.role_registry_id = frame.role_registry_id
    WHERE frame.frame_id = OLD.frame_id
)
BEGIN
    SELECT RAISE(ABORT, 'evaluation generation is sealed after terminal release');
END;

CREATE TRIGGER prevent_scoped_head_delete
BEFORE DELETE ON account_community_gold_head
BEGIN
    SELECT RAISE(ABORT, 'scoped gold heads are immutable; append a correction');
END;

CREATE TRIGGER validate_terminal_access_generation
BEFORE INSERT ON account_community_terminal_test_access
WHEN NEW.released_label_head_count <= 0 OR NOT EXISTS (
    SELECT 1 FROM account_community_evaluation_frame frame
    WHERE frame.frame_id = NEW.frame_id
      AND frame.role_registry_id = NEW.role_registry_id
)
BEGIN
    SELECT RAISE(ABORT, 'terminal access must bind a non-empty matching generation');
END;

CREATE TRIGGER prevent_immutable_terminal_access_update
BEFORE UPDATE ON account_community_terminal_test_access
BEGIN
    SELECT RAISE(ABORT, 'immutable terminal access receipt cannot be updated');
END;

CREATE TRIGGER prevent_immutable_terminal_access_delete
BEFORE DELETE ON account_community_terminal_test_access
BEGIN
    SELECT RAISE(ABORT, 'immutable terminal access receipt cannot be deleted');
END;

"""

INTEGRITY_TRIGGERS = (
    _CORE_INTEGRITY_TRIGGERS
    + "\n"
    + ONTOLOGY_FRAME_TRIGGERS
    + "\n"
    + PREDICTION_TRIGGERS
)
