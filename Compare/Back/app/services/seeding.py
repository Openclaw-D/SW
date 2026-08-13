from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.contracts.project_selection import ProjectCatalogItem
from app.contracts.workbench import WorkbenchProject
from app.models import (
    ApprovalState,
    AuditRecord,
    BusinessCorrection,
    EvidenceReference,
    FactVersion,
    Material,
    MaterialVersion,
    PolicyResult,
    Project,
    ProjectSnapshot,
    ReviewEvent,
    ReviewEvidenceTarget,
    RuleVersion,
    locator_from_mapping,
    new_id,
    utc_now,
)
from app.repositories import SQLiteStateRepository

from .generator_adapter import GeneratedProjectBundle, WorkbenchGeneratorAdapter
from .locators import LocatorService
from .native_sources import NativeSourceBinding, load_native_source_bindings


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _target(value: Mapping[str, Any]) -> ReviewEvidenceTarget:
    evidence_ref = str(value["evidenceRef"])
    refs = value.get("evidenceRefs") or [evidence_ref]
    return ReviewEvidenceTarget(
        evidence_ref=evidence_ref,
        evidence_refs=tuple(str(item) for item in refs),
        dimension_id=str(value["dimensionId"]),
        review_target_id=value.get("reviewTargetId"),
        fact_version_id=value.get("factVersionId"),
        unavailable_reason=value.get("unavailableReason"),
    )


class SeedService:
    def __init__(
        self,
        repository: SQLiteStateRepository,
        generator: WorkbenchGeneratorAdapter,
        import_root: Path | None = None,
    ) -> None:
        self.repository = repository
        self.generator = generator
        self.locators = LocatorService(repository)
        self.native_sources: dict[tuple[str, str], NativeSourceBinding] = (
            load_native_source_bindings(import_root) if import_root is not None else {}
        )

    def seed_once(self) -> int:
        seed_key = f"workbench:{self.generator.identity}"
        with self.repository.transaction(write=True) as connection:
            if self.repository.seed_run_exists(seed_key, connection):
                return 0
            # Generate only after the durable marker check.  A restart of an
            # already seeded 24-project database must not rebuild the full
            # deterministic fixture graph merely to discover it is present.
            bundles = tuple(self.generator.seed_bundles())
            if not bundles:
                return 0
            for bundle in bundles:
                self._seed_bundle(bundle, connection)
            self.repository.create_seed_run(
                seed_key=seed_key,
                source=self.generator.identity,
                project_count=len(bundles),
                connection=connection,
            )
        return len(bundles)

    def _seed_bundle(self, bundle: GeneratedProjectBundle, connection: Any) -> None:
        catalog = ProjectCatalogItem.model_validate(bundle.catalog)
        workbench = WorkbenchProject.model_validate(bundle.workbench)
        if catalog.project_id != workbench.project.id:
            raise ValueError("seed catalog projectId must match workbench.project.id")
        catalog_json = catalog.model_dump(by_alias=True, mode="json")
        workbench_json = workbench.model_dump(by_alias=True, mode="json")
        created_at = str(catalog_json["createdAt"])
        now = utc_now()
        project = Project(
            id=catalog.project_id,
            name=workbench.project.name,
            payload={
                "catalog": catalog_json,
                "dimensionSeries": list(bundle.dimension_series),
            },
            created_at=created_at,
            updated_at=now,
        )
        self.repository.create_project(project, connection)
        self.repository.create_project_snapshot(
            ProjectSnapshot(
                id=new_id("snapshot"),
                project_id=project.id,
                version=1,
                payload=workbench_json,
                created_at=now,
                created_by="generator",
            ),
            connection,
        )

        for item in workbench_json["materials"]:
            material_id = str(item["id"])
            version_id = str(item["versionId"])
            native_source = self.native_sources.get((project.id, material_id))
            material = Material(
                id=material_id,
                project_id=project.id,
                kind=str(item["kind"]),
                file_name=str(item["fileName"]),
                availability=str(item["availability"]),
                current_version_id=None,
                metadata={
                    "label": item["label"],
                    "sourceLabel": item["sourceLabel"],
                    "isSimulated": item["isSimulated"],
                    "folderPath": item.get("folderPath"),
                    "businessPath": item.get("businessPath"),
                },
                created_at=now,
            )
            self.repository.create_material(material, connection)
            version = MaterialVersion(
                id=version_id,
                project_id=project.id,
                material_id=material_id,
                version=1,
                mime_type=str(item["mimeType"]),
                content_hash=native_source.content_hash if native_source else _hash(item),
                payload=dict(item),
                created_at=now,
                created_by="generator",
            )
            self.repository.create_material_version(version, connection)
            self.repository.set_current_material_version(
                project.id, material_id, version_id, connection
            )

        for item in workbench_json["evidence"]:
            locator = locator_from_mapping(item["locator"]) if item.get("locator") else None
            evidence = EvidenceReference(
                id=str(item["id"]),
                project_id=project.id,
                label=str(item["label"]),
                locator=locator,
                location_status=str(item["locationStatus"]),
                material_status=str(item["materialStatus"]),
                created_at=now,
            )
            self.locators.validate_reference(project.id, evidence, connection)
            self.repository.create_evidence_reference(evidence, connection)

        facts: dict[str, FactVersion] = {}
        for item in workbench_json["facts"]:
            fact = FactVersion(
                id=str(item["id"]),
                project_id=project.id,
                fact_key=str(item["factKey"]),
                dimension_id=str(item["dimensionId"]),
                version=int(item["version"]),
                label=str(item["label"]),
                value=item.get("value"),
                unit=item.get("unit"),
                source=str(item["source"]),
                evidence_refs=tuple(str(ref) for ref in item["evidenceRefs"]),
                supersedes_version_id=None,
                created_at=str(item["createdAt"]),
                created_by="generator",
                is_simulated=bool(item["isSimulated"]),
            )
            self.repository.create_fact_version(fact, connection)
            facts[fact.id] = fact

        by_key: dict[str, list[FactVersion]] = {}
        for fact in facts.values():
            by_key.setdefault(fact.fact_key, []).append(fact)
        for versions in by_key.values():
            versions.sort(key=lambda item: item.version)

        for item in workbench_json["corrections"]:
            source = facts[str(item["fromFactVersionId"])]
            next_version = next(
                (
                    fact
                    for fact in by_key[source.fact_key]
                    if fact.version == source.version + 1
                ),
                source,
            )
            correction = BusinessCorrection(
                id=str(item["id"]),
                project_id=project.id,
                fact_key=str(item["factKey"]),
                from_fact_version_id=source.id,
                to_fact_version_id=next_version.id,
                expected_version=source.version,
                proposed_value=item.get("proposedValue"),
                reason=str(item["reason"]),
                evidence_refs=tuple(str(ref) for ref in item["evidenceRefs"]),
                status=str(item["status"]),
                created_by="business",
                created_at=str(item["createdAt"]),
                is_simulated=bool(item["isSimulated"]),
            )
            self.repository.create_business_correction(correction, connection)

        for item in workbench_json["reviewEvents"]:
            event = ReviewEvent(
                id=str(item["id"]),
                project_id=project.id,
                sequence=int(item["sequence"]),
                thread_id=str(item["threadId"]),
                reply_to_event_id=item.get("replyToEventId"),
                issue_status=str(item["issueStatus"]),
                event_type=str(item["eventType"]),
                actor=str(item["actor"]),
                actor_label=str(item["actorLabel"]),
                dimension_id=str(item["dimensionId"]),
                evidence_targets=tuple(_target(target) for target in item["evidenceTargets"]),
                review_target_id=item.get("reviewTargetId"),
                title=str(item["title"]),
                summary=str(item["summary"]),
                fact_version_ids=tuple(str(value) for value in item["factVersionIds"]),
                evidence_refs=tuple(str(value) for value in item["evidenceRefs"]),
                rule_refs=tuple(str(value) for value in item["ruleRefs"]),
                created_at=str(item["createdAt"]),
                immutable=True,
                is_simulated=bool(item["isSimulated"]),
            )
            self.repository.create_review_event(event, connection)

        policy_items: dict[str, dict[str, Any]] = {}
        for item in workbench_json["riskSummary"]["hardConstraintResults"]:
            policy_items[str(item["id"])] = item
        for determination in workbench_json["determinations"]:
            for item in determination["hardConstraintResults"]:
                policy_items[str(item["id"])] = item
        for item in policy_items.values():
            rule_id = str(item["ruleId"])
            version_name = str(item["ruleVersion"])
            definition = {
                "kind": "hard_constraint",
                "ruleId": rule_id,
                "version": version_name,
                "title": str(item["title"]),
                "scope": str(item["scope"]),
                "evidenceRequirement": str(item["evidenceRequirement"]),
                "responsibleParty": str(item["responsibleParty"]),
                "source": "generator_fixture",
            }
            definition_hash = _hash(definition)
            rule = self.repository.find_rule_version(rule_id, version_name, connection)
            if rule is None:
                rule = RuleVersion(
                    id=f"rule-version::{rule_id}::{version_name}",
                    rule_id=rule_id,
                    version=version_name,
                    title=str(item["title"]),
                    is_hard_gate=True,
                    definition=definition,
                    definition_hash=definition_hash,
                    created_at=now,
                    created_by="generator",
                )
                self.repository.create_rule_version(rule, connection)
            elif rule.definition_hash != definition_hash:
                raise ValueError(
                    f"rule version {rule_id}/{version_name} changed definition"
                )
            targets = tuple(_target(target) for target in item["evidenceTargets"])
            primary = _target(item["primaryTarget"]) if item.get("primaryTarget") else None
            incomplete_evidence = not targets
            for target in targets:
                for evidence_ref in target.evidence_refs:
                    resolution = self.locators.resolve(
                        project.id, evidence_ref, connection
                    )
                    if resolution.status != "located":
                        incomplete_evidence = True
            normalized_result = (
                "manual_review" if incomplete_evidence else str(item["result"])
            )
            explanation = str(item["explanation"])
            if incomplete_evidence and normalized_result == "manual_review":
                explanation = (
                    f"{explanation} 材料缺失或无法核验，仅进入人工复核，不形成否决。"
                ).strip()
            result = PolicyResult(
                id=str(item["id"]),
                project_id=project.id,
                rule_version_id=rule.id,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                title=str(item["title"]),
                result=normalized_result,
                evidence_targets=targets,
                primary_target=primary,
                scope=str(item["scope"]),
                evidence_requirement=str(item["evidenceRequirement"]),
                gate_triggered=(
                    bool(item["gateTriggered"]) and normalized_result == "block"
                ),
                responsible_party=str(item["responsibleParty"]),
                next_action=str(item["nextAction"]),
                explanation=explanation,
                evaluation_input={
                    "source": "generator_fixture",
                    "declaredResult": str(item["result"]),
                    "evidenceTargets": [target.to_dict() for target in targets],
                    "primaryTarget": primary.to_dict() if primary else None,
                    "gateTriggered": bool(item["gateTriggered"]),
                },
                evaluated_at=str(item["evaluatedAt"]),
                is_simulated=bool(item["isSimulated"]),
            )
            self.repository.create_policy_result(result, connection)

        self.repository.put_approval_state(
            ApprovalState(
                project_id=project.id,
                state="draft",
                version=1,
                decision_grade=None,
                updated_at=now,
                updated_by="system",
            ),
            connection,
        )
        audit_payload = {
            "generator": self.generator.identity,
            "snapshotVersion": 1,
            "materialCount": len(workbench_json["materials"]),
            "factCount": len(workbench_json["facts"]),
        }
        audit_created_at = now
        hash_payload = {
            "projectId": project.id,
            "sequence": 1,
            "action": "project_seeded",
            "aggregateType": "project",
            "aggregateId": project.id,
            "actor": "system",
            "payload": audit_payload,
            "previousHash": None,
            "createdAt": audit_created_at,
        }
        self.repository.create_audit_record(
            AuditRecord(
                id=new_id("audit"),
                project_id=project.id,
                sequence=1,
                action="project_seeded",
                aggregate_type="project",
                aggregate_id=project.id,
                actor="system",
                payload=audit_payload,
                previous_hash=None,
                event_hash=_hash(hash_payload),
                created_at=audit_created_at,
            ),
            connection,
        )
