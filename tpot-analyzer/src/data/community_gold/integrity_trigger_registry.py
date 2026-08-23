"""Names and replacement SQL for canonical Community Gold triggers."""

TRIGGER_NAMES = (
    "prevent_scoped_gold_update",
    "prevent_scoped_gold_delete",
    "prevent_scoped_gold_insert_after_release",
    "validate_scoped_gold_lineage_insert",
    "validate_scoped_gold_head_insert",
    "validate_scoped_gold_head_update",
    "prevent_scoped_head_insert_after_release",
    "prevent_scoped_head_update_after_release",
    "prevent_scoped_head_delete",
    "prevent_scoped_prediction_insert_after_release",
    "validate_scoped_prediction_binding",
    "validate_scoped_prediction_score",
    "prevent_unregistered_probability_insert",
    "prevent_scoped_prediction_update",
    "prevent_scoped_prediction_delete",
    "validate_terminal_access_generation",
    "prevent_immutable_terminal_access_update",
    "prevent_immutable_terminal_access_delete",
    "prevent_immutable_ontology_version_update",
    "prevent_immutable_ontology_version_delete",
    "validate_ontology_group_insert",
    "prevent_immutable_ontology_group_update",
    "prevent_immutable_ontology_group_delete",
    "prevent_immutable_ontology_task_update",
    "prevent_immutable_ontology_task_delete",
    "prevent_immutable_role_registry_update",
    "prevent_immutable_role_registry_delete",
    "prevent_immutable_global_role_update",
    "prevent_immutable_global_role_delete",
    "prevent_global_role_insert_after_frame",
    "prevent_frame_insert_after_release",
    "prevent_immutable_frame_update",
    "prevent_immutable_frame_delete",
    "prevent_immutable_frame_role_update",
    "prevent_immutable_frame_role_delete",
    "prevent_scoped_gold_community_delete",
)

_RETIRED_TRIGGER_NAMES = ("prevent_scoped_head_delete_after_release",)


def drop_integrity_triggers_sql() -> str:
    """Replace canonical triggers so stale definitions cannot survive."""

    return "\n".join(
        f"DROP TRIGGER IF EXISTS {name};"
        for name in (*TRIGGER_NAMES, *_RETIRED_TRIGGER_NAMES)
    )
