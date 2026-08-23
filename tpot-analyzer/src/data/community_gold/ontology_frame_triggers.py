"""SQLite immutability triggers for ontology, role, and frame records."""

ONTOLOGY_FRAME_TRIGGERS = """
CREATE TRIGGER prevent_immutable_ontology_version_update
BEFORE UPDATE ON personal_ontology_version
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology version cannot be updated');
END;

CREATE TRIGGER prevent_immutable_ontology_version_delete
BEFORE DELETE ON personal_ontology_version
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology version cannot be deleted');
END;

CREATE TRIGGER validate_ontology_group_insert
BEFORE INSERT ON personal_ontology_group
WHEN NOT EXISTS (
    SELECT 1
    FROM personal_ontology_version version,
         json_each(version.definition_json, '$.groups') group_entry
    WHERE version.user_id = NEW.user_id
      AND version.ontology_id = NEW.ontology_id
      AND version.ontology_version = NEW.ontology_version
      AND json_extract(group_entry.value, '$.communityId') = NEW.community_id
      AND json_extract(group_entry.value, '$.definition') =
          NEW.boundary_definition
)
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology definition does not contain group');
END;

CREATE TRIGGER prevent_immutable_ontology_group_update
BEFORE UPDATE ON personal_ontology_group
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology group cannot be updated');
END;

CREATE TRIGGER prevent_immutable_ontology_group_delete
BEFORE DELETE ON personal_ontology_group
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology group cannot be deleted');
END;

CREATE TRIGGER prevent_immutable_ontology_task_update
BEFORE UPDATE ON personal_ontology_task
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology task cannot be updated');
END;

CREATE TRIGGER prevent_immutable_ontology_task_delete
BEFORE DELETE ON personal_ontology_task
BEGIN
    SELECT RAISE(ABORT, 'immutable ontology task cannot be deleted');
END;

CREATE TRIGGER prevent_immutable_role_registry_update
BEFORE UPDATE ON account_community_role_registry
BEGIN
    SELECT RAISE(ABORT, 'immutable role registry cannot be updated');
END;

CREATE TRIGGER prevent_immutable_role_registry_delete
BEFORE DELETE ON account_community_role_registry
BEGIN
    SELECT RAISE(ABORT, 'immutable role registry cannot be deleted');
END;

CREATE TRIGGER prevent_immutable_global_role_update
BEFORE UPDATE ON account_community_global_role
BEGIN
    SELECT RAISE(ABORT, 'immutable global role cannot be updated');
END;

CREATE TRIGGER prevent_immutable_global_role_delete
BEFORE DELETE ON account_community_global_role
BEGIN
    SELECT RAISE(ABORT, 'immutable global role cannot be deleted');
END;

CREATE TRIGGER prevent_global_role_insert_after_frame
BEFORE INSERT ON account_community_global_role
WHEN EXISTS (
    SELECT 1 FROM account_community_evaluation_frame frame
    WHERE frame.role_registry_id = NEW.role_registry_id
)
BEGIN
    SELECT RAISE(ABORT, 'global role registry is sealed by a frozen frame');
END;

CREATE TRIGGER prevent_frame_insert_after_release
BEFORE INSERT ON account_community_evaluation_frame
WHEN EXISTS (
    SELECT 1 FROM account_community_terminal_test_access access
    WHERE access.role_registry_id = NEW.role_registry_id
)
BEGIN
    SELECT RAISE(ABORT, 'evaluation generation is sealed after terminal release');
END;

CREATE TRIGGER prevent_immutable_frame_update
BEFORE UPDATE ON account_community_evaluation_frame
BEGIN
    SELECT RAISE(ABORT, 'immutable evaluation frame cannot be updated');
END;

CREATE TRIGGER prevent_immutable_frame_delete
BEFORE DELETE ON account_community_evaluation_frame
BEGIN
    SELECT RAISE(ABORT, 'immutable evaluation frame cannot be deleted');
END;

CREATE TRIGGER prevent_immutable_frame_role_update
BEFORE UPDATE ON account_community_evaluation_role
BEGIN
    SELECT RAISE(ABORT, 'immutable evaluation role cannot be updated');
END;

CREATE TRIGGER prevent_immutable_frame_role_delete
BEFORE DELETE ON account_community_evaluation_role
BEGIN
    SELECT RAISE(ABORT, 'immutable evaluation role cannot be deleted');
END;

CREATE TRIGGER prevent_scoped_gold_community_delete
BEFORE DELETE ON community
WHEN EXISTS (
    SELECT 1 FROM account_community_gold_label_set
    WHERE community_id = OLD.id AND identity_status = 'scoped'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'cannot delete community referenced by immutable scoped gold history'
    );
END;
"""
