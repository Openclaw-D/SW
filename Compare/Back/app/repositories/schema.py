from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 8

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_snapshots (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version >= 1),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('excel', 'pdf', 'document', 'image', 'media', 'scene')),
    file_name TEXT NOT NULL,
    availability TEXT NOT NULL,
    current_version_id TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_materials_project ON materials(project_id);

CREATE TABLE IF NOT EXISTS material_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version >= 1),
    mime_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(material_id, version),
    UNIQUE(material_id, content_hash)
);
CREATE INDEX IF NOT EXISTS ix_material_versions_project ON material_versions(project_id);
CREATE INDEX IF NOT EXISTS ix_material_versions_material ON material_versions(material_id);

CREATE TABLE IF NOT EXISTS material_source_records (
    material_version_id TEXT PRIMARY KEY REFERENCES material_versions(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (
        classification IN ('authorized_customer', 'public_reference', 'synthetic_demo')
    ),
    authorization_ref TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_file_ref TEXT,
    byte_size INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_material_sources_project ON material_source_records(project_id);

CREATE TABLE IF NOT EXISTS material_imports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    manifest_ref TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS material_intelligence_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    material_version_id TEXT NOT NULL REFERENCES material_versions(id) ON DELETE RESTRICT,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'needs_review', 'unavailable')),
    provider TEXT,
    model TEXT,
    result_json TEXT NOT NULL,
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE(project_id, material_version_id, input_hash)
);
CREATE INDEX IF NOT EXISTS ix_material_intelligence_scope
    ON material_intelligence_runs(project_id, material_id, created_at);

CREATE TABLE IF NOT EXISTS source_anchors (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    material_version_id TEXT NOT NULL REFERENCES material_versions(id) ON DELETE RESTRICT,
    intelligence_run_id TEXT NOT NULL REFERENCES material_intelligence_runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extracted_fact_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    material_version_id TEXT NOT NULL REFERENCES material_versions(id) ON DELETE RESTRICT,
    intelligence_run_id TEXT NOT NULL REFERENCES material_intelligence_runs(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    dimension_id TEXT NOT NULL CHECK (
        dimension_id IN ('compliance', 'transaction', 'production', 'revenue', 'debt', 'cashflow')
    ),
    label TEXT NOT NULL,
    value_json TEXT NOT NULL,
    unit TEXT,
    candidate_status TEXT NOT NULL CHECK (
        candidate_status IN ('candidate', 'needs_review', 'conflicting')
    ),
    source_anchor_ids_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_candidates_project ON extracted_fact_candidates(project_id, created_at);

CREATE TABLE IF NOT EXISTS candidate_confirmations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES extracted_fact_candidates(id) ON DELETE RESTRICT,
    from_fact_version_id TEXT NOT NULL REFERENCES fact_versions(id) ON DELETE RESTRICT,
    to_fact_version_id TEXT NOT NULL REFERENCES fact_versions(id) ON DELETE RESTRICT,
    expected_version INTEGER NOT NULL CHECK (expected_version >= 1),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(project_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS scene_specs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    material_version_id TEXT NOT NULL REFERENCES material_versions(id) ON DELETE RESTRICT,
    intelligence_run_id TEXT NOT NULL REFERENCES material_intelligence_runs(id) ON DELETE CASCADE,
    source_anchor_ids_json TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scene_specs_scope ON scene_specs(project_id, material_id, created_at);

CREATE TABLE IF NOT EXISTS evidence_references (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    material_id TEXT REFERENCES materials(id) ON DELETE RESTRICT,
    material_version_id TEXT REFERENCES material_versions(id) ON DELETE RESTRICT,
    locator_kind TEXT,
    locator_json TEXT,
    location_status TEXT NOT NULL CHECK (
        location_status IN ('located', 'pending', 'unverifiable', 'version_mismatch')
    ),
    material_status TEXT NOT NULL CHECK (
        material_status IN ('confirmed', 'review', 'conflict')
    ),
    created_at TEXT NOT NULL,
    CHECK (
        (locator_json IS NULL AND material_id IS NULL AND material_version_id IS NULL
            AND location_status IN ('pending', 'unverifiable'))
        OR
        (locator_json IS NOT NULL AND material_id IS NOT NULL AND material_version_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_evidence_project ON evidence_references(project_id);
CREATE INDEX IF NOT EXISTS ix_evidence_material ON evidence_references(material_id);

CREATE TABLE IF NOT EXISTS fact_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fact_key TEXT NOT NULL,
    dimension_id TEXT NOT NULL CHECK (
        dimension_id IN ('compliance', 'transaction', 'production', 'revenue', 'debt', 'cashflow')
    ),
    version INTEGER NOT NULL CHECK (version >= 1),
    label TEXT NOT NULL,
    value_json TEXT NOT NULL,
    unit TEXT,
    source TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    supersedes_version_id TEXT REFERENCES fact_versions(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
    UNIQUE(project_id, fact_key, version)
);
CREATE INDEX IF NOT EXISTS ix_fact_versions_project_key
    ON fact_versions(project_id, fact_key, version DESC);

CREATE TABLE IF NOT EXISTS business_corrections (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fact_key TEXT NOT NULL,
    from_fact_version_id TEXT NOT NULL REFERENCES fact_versions(id) ON DELETE RESTRICT,
    to_fact_version_id TEXT NOT NULL REFERENCES fact_versions(id) ON DELETE RESTRICT,
    expected_version INTEGER NOT NULL CHECK (expected_version >= 1),
    proposed_value_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1))
);
CREATE INDEX IF NOT EXISTS ix_corrections_project ON business_corrections(project_id);

CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    thread_id TEXT NOT NULL,
    reply_to_event_id TEXT REFERENCES review_events(id) ON DELETE RESTRICT,
    issue_status TEXT NOT NULL CHECK (
        issue_status IN ('open', 'answered', 'pending_gate', 'resolved')
    ),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (actor IN ('business', 'risk', 'system')),
    actor_label TEXT NOT NULL,
    dimension_id TEXT NOT NULL CHECK (
        dimension_id IN ('compliance', 'transaction', 'production', 'revenue', 'debt', 'cashflow')
    ),
    evidence_targets_json TEXT NOT NULL,
    review_target_id TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    fact_version_ids_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    rule_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
    UNIQUE(project_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_review_events_project_sequence
    ON review_events(project_id, sequence);

CREATE TABLE IF NOT EXISTS rule_versions (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    version TEXT NOT NULL,
    title TEXT NOT NULL,
    is_hard_gate INTEGER NOT NULL CHECK (is_hard_gate IN (0, 1)),
    definition_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(rule_id, version)
);

CREATE TABLE IF NOT EXISTS policy_results (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rule_version_id TEXT NOT NULL REFERENCES rule_versions(id) ON DELETE RESTRICT,
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    title TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('pass', 'block', 'manual_review')),
    evidence_targets_json TEXT NOT NULL,
    primary_target_json TEXT,
    scope TEXT NOT NULL,
    evidence_requirement TEXT NOT NULL,
    gate_triggered INTEGER NOT NULL CHECK (gate_triggered IN (0, 1)),
    responsible_party TEXT NOT NULL CHECK (
        responsible_party IN ('business', 'risk', 'joint')
    ),
    next_action TEXT NOT NULL,
    explanation TEXT NOT NULL,
    evaluation_input_json TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1))
);
CREATE INDEX IF NOT EXISTS ix_policy_results_project ON policy_results(project_id, evaluated_at);

CREATE TABLE IF NOT EXISTS approval_states (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    decision_grade TEXT,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_transitions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    reason TEXT NOT NULL,
    policy_result_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, sequence)
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    key TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    action TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, sequence),
    UNIQUE(project_id, event_hash)
);

CREATE TABLE IF NOT EXISTS agent_threads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'closed', 'rejected')),
    focus_role TEXT NOT NULL CHECK (
        focus_role IN ('business', 'risk', 'leadership')
    ),
    version INTEGER NOT NULL CHECK (version >= 1),
    created_by_role TEXT NOT NULL CHECK (
        created_by_role IN ('business', 'risk', 'leadership')
    ),
    closed_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (status = 'active' AND closed_reason IS NULL)
        OR (status != 'active' AND length(trim(closed_reason)) > 0)
    ),
    UNIQUE(project_id, id)
);
CREATE INDEX IF NOT EXISTS ix_agent_threads_project_updated
    ON agent_threads(project_id, updated_at, id);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('business', 'risk', 'leadership')),
    mode TEXT NOT NULL CHECK (mode IN ('disabled', 'synthetic', 'real')),
    status TEXT NOT NULL CHECK (
        status IN (
            'running', 'completed', 'needs_review', 'out_of_scope',
            'failed', 'unavailable'
        )
    ),
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    expected_thread_version INTEGER NOT NULL CHECK (expected_thread_version >= 0),
    context_version TEXT NOT NULL,
    provider_id TEXT,
    model_id TEXT,
    prompt_version TEXT,
    lease_token TEXT NOT NULL,
    lease_until REAL NOT NULL,
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
    output_message_ids_json TEXT NOT NULL,
    output_hash TEXT,
    error_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only = 1),
    FOREIGN KEY(project_id, thread_id)
        REFERENCES agent_threads(project_id, id) ON DELETE CASCADE,
    UNIQUE(project_id, idempotency_key),
    UNIQUE(project_id, turn_id),
    UNIQUE(project_id, thread_id, run_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_runs_one_active_thread
    ON agent_runs(project_id, thread_id) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS ix_agent_runs_project_thread_started
    ON agent_runs(project_id, thread_id, started_at);

CREATE TABLE IF NOT EXISTS agent_messages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    role TEXT NOT NULL CHECK (role IN ('business', 'risk', 'leadership')),
    author_type TEXT NOT NULL CHECK (author_type IN ('human', 'agent')),
    kind TEXT NOT NULL CHECK (kind IN ('user_input', 'agent_reply')),
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    generated_content_json TEXT,
    execution_json TEXT,
    reply_to_message_id TEXT,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only = 1),
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
    CHECK (
        (author_type = 'human' AND kind = 'user_input'
         AND generated_content_json IS NULL AND execution_json IS NULL
         AND is_simulated = 0)
        OR
        (author_type = 'agent' AND kind = 'agent_reply'
         AND generated_content_json IS NOT NULL AND execution_json IS NOT NULL)
    ),
    FOREIGN KEY(project_id, thread_id)
        REFERENCES agent_threads(project_id, id) ON DELETE CASCADE,
    FOREIGN KEY(project_id, thread_id, reply_to_message_id)
        REFERENCES agent_messages(project_id, thread_id, id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id, thread_id, run_id)
        REFERENCES agent_runs(project_id, thread_id, run_id) ON DELETE RESTRICT,
    UNIQUE(project_id, thread_id, id),
    UNIQUE(project_id, thread_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_agent_messages_thread_sequence
    ON agent_messages(project_id, thread_id, sequence);

CREATE TABLE IF NOT EXISTS agent_run_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    step_index INTEGER NOT NULL CHECK (step_index = 1),
    role TEXT NOT NULL CHECK (role IN ('business', 'risk', 'leadership')),
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    context_version TEXT NOT NULL,
    output_hash TEXT,
    error_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only = 1),
    FOREIGN KEY(project_id, thread_id, run_id)
        REFERENCES agent_runs(project_id, thread_id, run_id) ON DELETE CASCADE,
    UNIQUE(run_id, step_index)
);
CREATE INDEX IF NOT EXISTS ix_agent_run_steps_project_run
    ON agent_run_steps(project_id, run_id, step_index);

CREATE TABLE IF NOT EXISTS agent_focus_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    kind TEXT NOT NULL CHECK (
        kind IN (
            'thread_created', 'thread_migrated', 'focus_transferred',
            'focus_returned', 'thread_closed', 'thread_rejected',
            'thread_reopened'
        )
    ),
    from_focus_role TEXT CHECK (
        from_focus_role IS NULL OR from_focus_role IN ('business', 'risk', 'leadership')
    ),
    to_focus_role TEXT NOT NULL CHECK (
        to_focus_role IN ('business', 'risk', 'leadership')
    ),
    actor_role TEXT NOT NULL CHECK (
        actor_role IN ('business', 'risk', 'leadership')
    ),
    reason TEXT NOT NULL,
    expected_version INTEGER NOT NULL CHECK (expected_version >= 0),
    resulting_version INTEGER NOT NULL CHECK (resulting_version >= 1),
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id, thread_id)
        REFERENCES agent_threads(project_id, id) ON DELETE RESTRICT,
    UNIQUE(project_id, thread_id, sequence),
    UNIQUE(project_id, thread_id, id)
);
CREATE INDEX IF NOT EXISTS ix_agent_focus_events_thread_sequence
    ON agent_focus_events(project_id, thread_id, sequence);

CREATE TABLE IF NOT EXISTS agent_idempotency_records (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, key)
);

CREATE TRIGGER IF NOT EXISTS agent_threads_no_delete
BEFORE DELETE ON agent_threads
BEGIN
    SELECT RAISE(ABORT, 'audit root cannot be deleted: agent_threads');
END;

CREATE TRIGGER IF NOT EXISTS agent_runs_no_delete
BEFORE DELETE ON agent_runs
BEGIN
    SELECT RAISE(ABORT, 'audit root cannot be deleted: agent_runs');
END;

CREATE TABLE IF NOT EXISTS seed_runs (
    seed_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    project_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


IMMUTABLE_TABLES = (
    "project_snapshots",
    "material_versions",
    "material_source_records",
    "material_imports",
    "material_intelligence_runs",
    "source_anchors",
    "extracted_fact_candidates",
    "candidate_confirmations",
    "scene_specs",
    "evidence_references",
    "fact_versions",
    "business_corrections",
    "review_events",
    "rule_versions",
    "policy_results",
    "approval_transitions",
    "idempotency_records",
    "audit_records",
    "agent_messages",
    "agent_run_steps",
    "agent_focus_events",
    "agent_idempotency_records",
)


def immutable_trigger_sql(table: str) -> str:
    return f"""
    CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
    BEFORE UPDATE ON {table}
    BEGIN
        SELECT RAISE(ABORT, 'immutable table: {table}');
    END;
    CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
    BEFORE DELETE ON {table}
    BEGIN
        SELECT RAISE(ABORT, 'immutable table: {table}');
    END;
    """


def migrate_agent_schema(connection: sqlite3.Connection) -> None:
    """Replace the unpublished P6 multi-channel candidate with schema v8.

    The P6 candidate was never a release, but local restart evidence can contain
    its schema.  Preserve its advisory transcript and run audit while removing
    the obsolete ACL/governance surface.  New databases return immediately.
    """

    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'agent_threads'"
    ).fetchone()
    if table is None:
        return
    columns = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in connection.execute("PRAGMA table_info(agent_threads)")
    }
    if "focus_role" in columns:
        return

    false_advisory = connection.execute(
        "SELECT COUNT(*) FROM agent_messages WHERE advisory_only != 1"
    ).fetchone()[0]
    if false_advisory:
        raise sqlite3.IntegrityError(
            "legacy Agent messages contain non-advisory rows; migration refused"
        )

    connection.execute("PRAGMA foreign_keys=OFF")
    try:
        connection.executescript(
            """
            BEGIN IMMEDIATE;

            CREATE TABLE agent_threads_v8 (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('active', 'closed', 'rejected')),
                focus_role TEXT NOT NULL CHECK (focus_role IN ('business', 'risk', 'leadership')),
                version INTEGER NOT NULL CHECK (version >= 1),
                created_by_role TEXT NOT NULL CHECK (created_by_role IN ('business', 'risk', 'leadership')),
                closed_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (
                    (status = 'active' AND closed_reason IS NULL)
                    OR (status != 'active' AND length(trim(closed_reason)) > 0)
                ),
                UNIQUE(project_id, id)
            );

            INSERT INTO agent_threads_v8
                (id, project_id, title, status, focus_role, version,
                 created_by_role, closed_reason, created_at, updated_at)
            SELECT id, project_id, title, status, 'business', version,
                   created_by_role,
                   CASE WHEN status = 'active' THEN NULL
                        ELSE '从旧 P6 候选迁移的已关闭协作会话。' END,
                   created_at, updated_at
            FROM agent_threads;

            CREATE TABLE agent_runs_v8 (
                run_id TEXT PRIMARY KEY,
                turn_id TEXT NOT NULL,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('business', 'risk', 'leadership')),
                mode TEXT NOT NULL CHECK (mode IN ('disabled', 'synthetic', 'real')),
                status TEXT NOT NULL CHECK (
                    status IN ('running', 'completed', 'needs_review', 'out_of_scope', 'failed', 'unavailable')
                ),
                idempotency_key TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                expected_thread_version INTEGER NOT NULL CHECK (expected_thread_version >= 0),
                context_version TEXT NOT NULL,
                provider_id TEXT,
                model_id TEXT,
                prompt_version TEXT,
                lease_token TEXT NOT NULL,
                lease_until REAL NOT NULL,
                attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
                output_message_ids_json TEXT NOT NULL,
                output_hash TEXT,
                error_json TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only = 1),
                FOREIGN KEY(project_id, thread_id)
                    REFERENCES agent_threads_v8(project_id, id) ON DELETE CASCADE,
                UNIQUE(project_id, idempotency_key),
                UNIQUE(project_id, turn_id),
                UNIQUE(project_id, thread_id, run_id)
            );

            INSERT INTO agent_runs_v8
                (run_id, turn_id, project_id, thread_id, role, mode, status,
                 idempotency_key, request_fingerprint, input_hash,
                 expected_thread_version, context_version, provider_id, model_id,
                 prompt_version, lease_token, lease_until, attempt_count,
                 output_message_ids_json, output_hash, error_json, started_at,
                 finished_at, advisory_only)
            SELECT r.run_id, r.turn_id, r.project_id, r.thread_id, r.role, r.mode,
                   r.status, r.idempotency_key, r.request_fingerprint, r.input_hash,
                   r.expected_thread_version, r.input_hash, r.provider_id, r.model_id,
                   r.prompt_version, r.lease_token, r.lease_until, r.attempt_count,
                   r.output_message_ids_json,
                   (SELECT s.output_hash FROM agent_run_steps s
                    WHERE s.run_id = r.run_id AND s.step_index = 1),
                   r.error_json, r.started_at, r.finished_at, 1
            FROM agent_runs r;

            CREATE TABLE agent_messages_v8 (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                thread_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence >= 1),
                role TEXT NOT NULL CHECK (role IN ('business', 'risk', 'leadership')),
                author_type TEXT NOT NULL CHECK (author_type IN ('human', 'agent')),
                kind TEXT NOT NULL CHECK (kind IN ('user_input', 'agent_reply')),
                content TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                generated_content_json TEXT,
                execution_json TEXT,
                reply_to_message_id TEXT,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only = 1),
                is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
                CHECK (
                    (author_type = 'human' AND kind = 'user_input'
                     AND generated_content_json IS NULL AND execution_json IS NULL
                     AND is_simulated = 0)
                    OR
                    (author_type = 'agent' AND kind = 'agent_reply'
                     AND generated_content_json IS NOT NULL AND execution_json IS NOT NULL)
                ),
                FOREIGN KEY(project_id, thread_id)
                    REFERENCES agent_threads_v8(project_id, id) ON DELETE CASCADE,
                FOREIGN KEY(project_id, thread_id, reply_to_message_id)
                    REFERENCES agent_messages_v8(project_id, thread_id, id) ON DELETE RESTRICT,
                FOREIGN KEY(project_id, thread_id, run_id)
                    REFERENCES agent_runs_v8(project_id, thread_id, run_id) ON DELETE RESTRICT,
                UNIQUE(project_id, thread_id, id),
                UNIQUE(project_id, thread_id, sequence)
            );

            INSERT INTO agent_messages_v8
                (id, project_id, thread_id, sequence, role, author_type, kind,
                 content, citations_json, generated_content_json, execution_json,
                 reply_to_message_id, run_id, created_at, advisory_only, is_simulated)
            SELECT m.id, m.project_id, m.thread_id, m.sequence, m.author_role,
                   m.author_type,
                   CASE WHEN m.author_type = 'human' THEN 'user_input' ELSE 'agent_reply' END,
                   m.content, m.citations_json, m.generated_content_json,
                   CASE WHEN m.author_type = 'human' THEN NULL ELSE json_object(
                       'mode', r.mode,
                       'providerId', r.provider_id,
                       'modelId', r.model_id,
                       'promptVersion', r.prompt_version,
                       'inputHash', r.input_hash,
                       'contextVersion', r.input_hash,
                       'outputHash', (SELECT s.output_hash FROM agent_run_steps s
                                      WHERE s.run_id = r.run_id AND s.step_index = 1),
                       'advisoryOnly', json('true'),
                       'isSimulated', json(CASE WHEN r.mode = 'synthetic' THEN 'true' ELSE 'false' END),
                       'dataStatus', CASE r.mode
                           WHEN 'synthetic' THEN 'simulated'
                           WHEN 'real' THEN 'provider_generated_unverified'
                           ELSE 'unavailable' END,
                       'source', CASE WHEN r.mode = 'disabled' THEN 'agent_disabled' ELSE r.provider_id END,
                       'disclaimer', '迁移自未发布 P6 候选；内容仍为 advisory-only。'
                   ) END,
                   m.reply_to_message_id, m.run_id, m.created_at, 1,
                   CASE WHEN m.author_type = 'human' THEN 0 ELSE m.is_simulated END
            FROM agent_messages m
            JOIN agent_runs r ON r.project_id = m.project_id
                             AND r.thread_id = m.thread_id
                             AND r.run_id = m.run_id;

            CREATE TABLE agent_run_steps_v8 (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                thread_id TEXT NOT NULL,
                step_index INTEGER NOT NULL CHECK (step_index = 1),
                role TEXT NOT NULL CHECK (role IN ('business', 'risk', 'leadership')),
                status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
                provider_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                context_version TEXT NOT NULL,
                output_hash TEXT,
                error_json TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only = 1),
                FOREIGN KEY(project_id, thread_id, run_id)
                    REFERENCES agent_runs_v8(project_id, thread_id, run_id) ON DELETE CASCADE,
                UNIQUE(run_id, step_index)
            );

            INSERT INTO agent_run_steps_v8
                (id, run_id, project_id, thread_id, step_index, role, status,
                 provider_id, model_id, prompt_version, input_hash,
                 context_version, output_hash, error_json, started_at,
                 finished_at, advisory_only)
            SELECT id, run_id, project_id, thread_id, 1, role, status,
                   provider_id, model_id, prompt_version, input_hash,
                   context_version, output_hash, error_json, started_at,
                   finished_at, 1
            FROM agent_run_steps WHERE step_index = 1;

            CREATE TABLE agent_focus_events_v8 (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                thread_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence >= 1),
                kind TEXT NOT NULL,
                from_focus_role TEXT,
                to_focus_role TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                reason TEXT NOT NULL,
                expected_version INTEGER NOT NULL,
                resulting_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id, thread_id)
                    REFERENCES agent_threads_v8(project_id, id) ON DELETE RESTRICT,
                UNIQUE(project_id, thread_id, sequence),
                UNIQUE(project_id, thread_id, id)
            );

            INSERT INTO agent_focus_events_v8
                (id, project_id, thread_id, sequence, kind, from_focus_role,
                 to_focus_role, actor_role, reason, expected_version,
                 resulting_version, created_at)
            SELECT 'agent-focus-migrated-' || replace(id, 'agent-thread-', ''),
                   project_id, id, 1, 'thread_migrated', NULL, 'business',
                   created_by_role,
                   '从未发布的多频道 P6 候选迁移为单焦点协作会话。',
                   0, version, updated_at
            FROM agent_threads;

            CREATE TABLE agent_idempotency_records_v8 (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                operation TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(project_id, key)
            );
            INSERT INTO agent_idempotency_records_v8 SELECT * FROM agent_idempotency_records;

            DROP TABLE agent_messages;
            DROP TABLE agent_run_steps;
            DROP TABLE agent_governance_events;
            DROP TABLE agent_channel_access;
            DROP TABLE agent_governance_state;
            DROP TABLE agent_idempotency_records;
            DROP TABLE agent_runs;
            DROP TABLE agent_threads;

            ALTER TABLE agent_threads_v8 RENAME TO agent_threads;
            ALTER TABLE agent_runs_v8 RENAME TO agent_runs;
            ALTER TABLE agent_messages_v8 RENAME TO agent_messages;
            ALTER TABLE agent_run_steps_v8 RENAME TO agent_run_steps;
            ALTER TABLE agent_focus_events_v8 RENAME TO agent_focus_events;
            ALTER TABLE agent_idempotency_records_v8 RENAME TO agent_idempotency_records;
            COMMIT;
            """
        )
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys=ON")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError("Agent v8 migration failed foreign key check")
