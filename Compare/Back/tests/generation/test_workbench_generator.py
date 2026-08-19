from __future__ import annotations

from collections import Counter
import json
from types import SimpleNamespace

import pytest

from app.contracts.project_selection import ProjectCatalogItem
from app.contracts.material_schema import P5_ORIGINAL_MATERIAL_COUNT
from app.contracts.workbench import (
    AvailableDimensionSeriesResponse,
    DimensionSeriesRequest,
    ReviewEvidenceSelectionGroup,
    WorkbenchProject,
)
from app.domain.grading import equal_weighted_score
from app.domain.repayment import classify_repayment_structure
from app.fixtures.equipment_configurations import EQUIPMENT_CONFIGURATION_PROFILES
from app.services.generation import (
    DEFAULT_GENERATOR_SEED,
    DEFAULT_PROJECT_COUNT,
    PUBLIC_DEMO_PROJECT_COUNT,
    create_workbench_generator,
    generate_project_bundle,
    generate_project_bundles,
)
from app.services.generation.generator import P5_MATERIAL_COVERAGE
from scripts.verify_native_material_packs import has_formula_element


@pytest.fixture(scope="module")
def bundles() -> tuple[dict, ...]:
    # Historical coverage keeps exercising the explicitly opt-in varied profile.
    return generate_project_bundles(profile="varied")


@pytest.fixture(scope="module")
def provider(bundles: tuple[dict, ...]):
    value = create_workbench_generator(SimpleNamespace(generator_seed=DEFAULT_GENERATOR_SEED))
    value._bundles = bundles
    return value


def _detail(workbench: dict, dimension_id: str) -> dict:
    return next(item for item in workbench["dimensionDetails"] if item["dimensionId"] == dimension_id)


def _metric(detail: dict, metric_id: str) -> dict:
    return next(item for item in detail["metrics"] if item["id"] == metric_id)


def _line(workbench: dict) -> dict:
    return workbench["financedEquipment"]["lines"][0]


def test_default_generator_produces_24_strict_front_contract_bundles(bundles: tuple[dict, ...]) -> None:
    assert len(bundles) == DEFAULT_PROJECT_COUNT == 24
    for bundle in bundles:
        catalog = ProjectCatalogItem.model_validate(bundle["catalog"])
        workbench = WorkbenchProject.model_validate(bundle["workbench"])
        assert catalog.project_id == workbench.project.id
        assert len(bundle["dimensionSeries"]) == 4
        for group in bundle["selectionGroups"]:
            ReviewEvidenceSelectionGroup.model_validate(group)


def test_runtime_profile_seeds_exactly_one_public_demo_project() -> None:
    settings = SimpleNamespace(
        generator_seed=DEFAULT_GENERATOR_SEED,
        generator_profile="standard",
        demo_project_count=PUBLIC_DEMO_PROJECT_COUNT,
    )
    generator = create_workbench_generator(settings)

    assert generator.count == PUBLIC_DEMO_PROJECT_COUNT == 1
    assert len(generator.seed_bundles()) == 1


def test_public_standard_profile_has_24_unique_isolated_projects_and_one_fact_template() -> None:
    bundles = generate_project_bundles(profile="standard")
    assert len(bundles) == 24
    project_ids = [item["catalog"]["projectId"] for item in bundles]
    assert len(project_ids) == len(set(project_ids)) == 24
    assert {item["generation"]["pattern"] for item in bundles} == {"confirm"}
    # The full template is structurally identical while every persisted entity
    # is namespaced by its unique project ID.
    fact_keys = [tuple(sorted(fact["factKey"] for fact in item["workbench"]["facts"])) for item in bundles]
    material_categories = [tuple(material["id"].rsplit("-", 1)[-1] for material in item["workbench"]["materials"]) for item in bundles]
    assert len(set(fact_keys)) == len(set(material_categories)) == 1
    for bundle in bundles:
        project_id = bundle["catalog"]["projectId"]
        assert bundle["workbench"]["project"]["id"] == project_id
        assert all(project_id in material["id"] for material in bundle["workbench"]["materials"])
        assert all(project_id in fact["id"] for fact in bundle["workbench"]["facts"])


def test_same_seed_is_canonical_json_identical_and_other_seed_changes_all_layers() -> None:
    left = generate_project_bundle(4142, 7).to_mapping()
    again = generate_project_bundle(4142, 7).to_mapping()
    other = generate_project_bundle(4143, 7).to_mapping()
    assert json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(again, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert left["catalog"]["projectId"] != other["catalog"]["projectId"]
    assert left["catalog"]["amountWan"] != other["catalog"]["amountWan"]
    assert left["workbench"]["facts"] != other["workbench"]["facts"]
    assert left["workbench"]["materials"] != other["workbench"]["materials"]
    assert left["dimensionSeries"] != other["dimensionSeries"]


def test_projects_cover_six_industries_customers_and_all_five_global_risk_levels(bundles: tuple[dict, ...]) -> None:
    assert len({bundle["catalog"]["projectId"] for bundle in bundles}) == 24
    assert len({bundle["catalog"]["companyName"] for bundle in bundles}) == 24
    assert len({bundle["catalog"]["industry"] for bundle in bundles}) == 6
    levels = Counter(bundle["catalog"]["riskLevel"] for bundle in bundles)
    assert set(levels) == {"support", "attention", "confirm", "risk", "forbid"}
    assert all(levels[level] >= 4 for level in levels)
    global_evidence_ids = [item["id"] for bundle in bundles for item in bundle["workbench"]["evidence"]]
    assert len(global_evidence_ids) == len(set(global_evidence_ids))


def test_customer_industry_and_equipment_variants_change_facts_scores_and_observations(bundles: tuple[dict, ...]) -> None:
    fact_fingerprints = {
        tuple((fact["factKey"], fact["value"]) for fact in bundle["workbench"]["facts"][:29])
        for bundle in bundles
    }
    score_fingerprints = {
        tuple(item["score"] for item in bundle["workbench"]["dimensions"])
        for bundle in bundles
    }
    equipment_models = {_line(bundle["workbench"])["model"] for bundle in bundles}
    observation_fingerprints = {
        tuple(item["value"] for item in bundle["dimensionSeries"][0]["observations"][:10])
        for bundle in bundles
    }
    assert len(fact_fingerprints) == 24
    assert len(score_fingerprints) >= 20
    assert len(equipment_models) == 18
    assert len(observation_fingerprints) == 24


def test_six_dimensions_are_frozen_equal_weighted_and_not_polluted_by_guarantee(bundles: tuple[dict, ...]) -> None:
    expected = ["compliance", "transaction", "production", "revenue", "debt", "cashflow"]
    for bundle in bundles:
        workbench = bundle["workbench"]
        dimensions = workbench["dimensions"]
        assert [item["id"] for item in dimensions] == expected
        assert [item["dimensionId"] for item in workbench["dimensionDetails"]] == expected
        assert equal_weighted_score(item["score"] for item in dimensions) == pytest.approx(
            sum(item["score"] for item in dimensions) / 6, abs=0.05
        )
        assert "guarantee" not in {item["id"] for item in dimensions}
        assert "guarantee" not in {item["dimensionId"] for item in workbench["dimensionDetails"]}


def test_transaction_amounts_reconcile_and_price_benchmark_stays_in_equipment(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        catalog = bundle["catalog"]
        workbench = bundle["workbench"]
        ledger = workbench["financedEquipment"]
        line = _line(workbench)
        project_yuan = line["quantity"] * line["contractUnitPrice"]
        ratio_fact = next(item for item in workbench["facts"] if item["factKey"] == "transaction.financing_ratio")
        financed_fact = next(item for item in workbench["facts"] if item["factKey"] == "transaction.financed_amount_wan")
        assert project_yuan == pytest.approx(catalog["amountWan"] * 10_000, abs=0.01)
        assert financed_fact["value"] == pytest.approx(catalog["amountWan"] * ratio_fact["value"], abs=0.011)
        assert ledger["downPaymentAmount"] + financed_fact["value"] * 10_000 == pytest.approx(project_yuan, abs=0.011)
        transaction = _detail(workbench, "transaction")
        assert all("基准" not in item["label"] and "报价" not in item["label"] for item in transaction["metrics"])
        assert line["priceBenchmark"]["status"] == "available"
        assert line["priceBenchmark"]["low"] <= line["priceBenchmark"]["median"] <= line["priceBenchmark"]["high"]


def test_actual_repayment_schedule_reconciles_and_structure_is_not_randomized(bundles: tuple[dict, ...]) -> None:
    seen = set()
    for bundle in bundles:
        schedule = bundle["workbench"]["financedEquipment"]["repaymentSchedule"]
        facts = {item["factKey"]: item["value"] for item in bundle["workbench"]["facts"]}
        points = schedule["points"]
        structure = classify_repayment_structure(points)
        seen.add(structure)
        assert structure == facts["transaction.repayment"]
        assert len(points) == schedule["termMonths"] == facts["transaction.term_months"]
        assert sum(item["principal"] for item in points) == pytest.approx(facts["transaction.financed_amount_wan"] * 10_000, abs=0.02)
        assert all(item["rent"] == pytest.approx(item["principal"] + item["interest"], abs=0.011) for item in points)
    assert seen == {"front_loaded", "balanced", "back_loaded"}


def test_equipment_configuration_uses_exact_industry_equipment_model_profile(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        line = _line(bundle["workbench"])
        profile = EQUIPMENT_CONFIGURATION_PROFILES[line["equipment"]]
        assert profile.model == line["model"]
        assert {row["id"] for row in line["configuration"]["rows"]} == {
            f"config-{profile.id}-{spec.id}" for spec in profile.parameters
        }
        assert all(row["factVersionId"] and row["evidenceRefs"] for row in line["configuration"]["rows"])


def test_revenue_profit_debt_exposure_and_cashflow_totals_are_internally_consistent(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        workbench = bundle["workbench"]
        revenue = _detail(workbench, "revenue")
        annual = float(_metric(revenue, "revenue-income-metric")["value"].replace(",", "").split()[0])
        profit = float(_metric(revenue, "revenue-net-profit-metric")["value"].replace(",", "").split()[0])
        profitability = next(item for item in revenue["compositions"] if item["id"] == "revenue-profitability")
        assert sum(item["value"] for item in profitability["segments"]) == pytest.approx(annual, abs=0.02)
        assert next(item for item in profitability["segments"] if item["id"] == "revenue-profit-net-profit")["value"] == pytest.approx(profit, abs=0.01)
        debt = _detail(workbench, "debt")
        exposure = next(item for item in debt["compositions"] if item["id"] == "debt-project-exposure")
        total = float(_metric(debt, "debt-exposure-total")["value"].removesuffix("W").replace(",", ""))
        assert [item["label"] for item in exposure["segments"]] == ["200直", "200核心", "300核心", "500核心"]
        assert sum(item["value"] for item in exposure["segments"]) == pytest.approx(total, abs=0.02)
        assert total <= 1000
        assert sum(int(item["note"].split("份额", 1)[1].split("%", 1)[0]) for item in exposure["segments"]) == 100


def test_every_generated_reference_resolves_and_excel_business_rows_start_at_four(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        workbench = bundle["workbench"]
        evidence_by_id = {item["id"]: item for item in workbench["evidence"]}
        assert len(evidence_by_id) == len(workbench["evidence"])
        for item in workbench["evidence"]:
            if item["locator"] is None:
                assert item["locationStatus"] == "pending"
                continue
            assert item["locationStatus"] == "located"
            if item["locator"]["kind"] == "excel":
                start_row = int("".join(char for char in item["locator"]["range"].split(":", 1)[0] if char.isdigit()))
                assert start_row >= 4


def test_all_front_clickable_metrics_chart_points_and_evidence_chips_have_refs(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        workbench = bundle["workbench"]
        for detail in workbench["dimensionDetails"]:
            assert all(item["evidenceRefs"] for item in detail["metrics"])
            assert all(item["evidenceRefs"] for item in detail["breakdown"])
            for point in detail["series"]:
                assert all(measure["evidenceRefs"] for measure in point["measures"])
            for group in detail.get("seriesGroups") or []:
                for point in group["points"]:
                    assert all(measure["evidenceRefs"] for measure in point["measures"])
            for composition in detail.get("compositions") or []:
                assert all(segment["evidenceRefs"] for segment in composition["segments"])
        line = _line(workbench)
        assert line["contractEvidenceRefs"] and line["supplierQuoteEvidenceRefs"]
        assert all(row["evidenceRefs"] for row in line["configuration"]["rows"])
        assert all(point["evidenceRefs"] for point in workbench["financedEquipment"]["repaymentSchedule"]["points"])
        assert all(point["electricityEvidenceRefs"] and point["outputEvidenceRefs"] for point in workbench["productionEnergy"]["points"])
        production = _detail(workbench, "production")
        payroll = next(group for group in production["seriesGroups"] if group["id"] == "production-payroll")
        assert all(point["id"].startswith("timeseries-") for point in payroll["points"])


def test_multi_evidence_selection_groups_are_atomic_and_version_consistent(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        workbench = bundle["workbench"]
        evidence_by_id = {item["id"]: item for item in workbench["evidence"]}
        multi = [group for group in bundle["selectionGroups"] if len(group["targets"]) > 1]
        assert multi
        for group in multi:
            refs = [target["evidenceRef"] for target in group["targets"]]
            assert all(target["evidenceRefs"] == refs for target in group["targets"])
            for ref in refs:
                evidence = evidence_by_id[ref]
                if evidence["locator"] is not None:
                    material = next(item for item in workbench["materials"] if item["id"] == evidence["locator"]["materialId"])
                    assert evidence["locator"]["materialVersionId"] == material["versionId"]


def test_missing_material_only_lowers_confidence_and_requires_manual_review(bundles: tuple[dict, ...]) -> None:
    confirm = next(bundle for bundle in bundles if bundle["catalog"]["riskLevel"] == "confirm")
    workbench = confirm["workbench"]
    duplicate = next(item for item in workbench["facts"] if item["factKey"] == "debt.duplicate_registration")
    evidence = next(item for item in workbench["evidence"] if item["id"] == duplicate["evidenceRefs"][0])
    constraint = next(item for item in workbench["riskSummary"]["hardConstraintResults"] if item["ruleId"] == "DEBT-H-001")
    assert evidence["locator"] is None and evidence["locationStatus"] == "pending"
    assert constraint["result"] == "manual_review"
    assert constraint["gateTriggered"] is False
    assert workbench["riskSummary"]["decisionGrade"] != "E"
    assert workbench["riskSummary"]["pendingHumanDeterminations"]


def test_verified_adverse_fact_can_block_without_changing_score_grade_semantics(bundles: tuple[dict, ...]) -> None:
    forbidden = next(bundle for bundle in bundles if bundle["catalog"]["riskLevel"] == "forbid")
    summary = forbidden["workbench"]["riskSummary"]
    assert any(item["result"] == "block" and item["gateTriggered"] for item in summary["hardConstraintResults"])
    assert summary["decisionGrade"] == "E"
    assert summary["scoreGrade"] == forbidden["workbench"]["dimensions"][0]["scoreGrade"] or summary["scoreGrade"] in {"A", "B", "C", "D", "E"}


@pytest.mark.parametrize("grain", ["day", "week", "month", "year"])
def test_provider_queries_raw_observations_at_all_grains(grain: str, provider) -> None:
    bundle = provider.seed_bundles()[0]
    series = next(item for item in bundle["dimensionSeries"] if item["dimensionId"] == "revenue")
    request = DimensionSeriesRequest.model_validate({
        "projectId": bundle["catalog"]["projectId"], "dimensionId": "revenue",
        "metricIds": [item["id"] for item in series["metrics"]], "grain": grain,
        "startDate": series["observations"][0]["date"], "endDate": series["observations"][-1]["date"],
        "timezone": "Asia/Shanghai",
    })
    response = provider.query_dimension_series(request)
    validated = AvailableDimensionSeriesResponse.model_validate(response)
    assert validated.points
    assert all(measure.evidence_refs for point in validated.points for measure in point.measures)


def test_generator_identity_and_payload_are_explicitly_simulated(bundles: tuple[dict, ...]) -> None:
    provider = create_workbench_generator(SimpleNamespace(generator_seed=731))
    assert "731" in provider.identity
    for bundle in bundles:
        assert bundle["generation"]["source"] == "deterministic_business_rules"
        assert bundle["catalog"]["isSimulated"] is True
        assert bundle["workbench"]["project"]["dataStatus"] == "simulated"
        assert bundle["workbench"]["project"]["isSimulated"] is True
        assert "统计验证" in bundle["workbench"]["project"]["disclaimer"]
        fact_keys = {item["factKey"].lower() for item in bundle["workbench"]["facts"]}
        assert not any(any(token in key for token in ("approval", "outcome", "decision")) for key in fact_keys)


def test_native_pack_formula_detection_accepts_ooxml_namespace_prefixes() -> None:
    assert has_formula_element('<worksheet><f>A1+B1</f></worksheet>')
    assert has_formula_element('<x:worksheet xmlns:x="urn:test"><x:f>A1+B1</x:f></x:worksheet>')
    assert not has_formula_element('<worksheet><v>3</v></worksheet>')


def test_p5_material_pack_covers_every_required_category_and_every_material_has_evidence(bundles: tuple[dict, ...]) -> None:
    global_material_ids: list[str] = []
    global_version_ids: list[str] = []
    for bundle in bundles:
        workbench = bundle["workbench"]
        assert len(workbench["materials"]) == P5_ORIGINAL_MATERIAL_COUNT
        material_ids = {item["id"] for item in workbench["materials"]}
        version_ids = {item["versionId"] for item in workbench["materials"]}
        global_material_ids.extend(material_ids)
        global_version_ids.extend(version_ids)
        for dimension, categories in P5_MATERIAL_COVERAGE.items():
            for category in categories:
                expected = f"mat-{workbench['project']['id']}-{dimension}-{category}"
                assert expected in material_ids
        evidence_materials = {
            item["locator"]["materialId"]
            for item in workbench["evidence"]
            if item["locator"] is not None
        }
        assert material_ids <= evidence_materials
        assert all(
            item["locator"] is None
            or item["locator"]["materialVersionId"] in version_ids
            for item in workbench["evidence"]
        )
    assert len(global_material_ids) == len(set(global_material_ids)) == 1344
    assert len(global_version_ids) == len(set(global_version_ids)) == 1344


def test_p5_cross_material_company_contract_equipment_amount_and_periods_reconcile(bundles: tuple[dict, ...]) -> None:
    for bundle in bundles:
        workbench = bundle["workbench"]
        project = bundle["catalog"]
        materials = {item["id"].rsplit(f"{workbench['project']['id']}-", 1)[-1]: item for item in workbench["materials"]}
        lease_lines = materials["transaction-lease-contract"]["pages"][0]["lines"]
        purchase_lines = materials["transaction-purchase-contract"]["pages"][0]["lines"]
        equipment_row = materials["transaction-equipment-list"]["sheets"][0]["rows"][0]
        contract_no = next(line.split("：", 1)[1] for line in lease_lines if line.startswith("合同号："))
        assert project["companyName"] in lease_lines
        assert f"关联租赁合同：{contract_no}" in purchase_lines
        assert equipment_row[1] == contract_no
        assert equipment_row[4] == workbench["financedEquipment"]["lines"][0]["model"]
        assert equipment_row[5] == workbench["financedEquipment"]["lines"][0]["quantity"] == 2
        assert equipment_row[7] == pytest.approx(project["amountWan"], abs=0.001)
        invoice_rows = materials["transaction-equipment-invoices"]["sheets"][0]["rows"]
        assert sum(row[4] for row in invoice_rows) == pytest.approx(project["amountWan"], abs=0.001)
        statement_rows = materials["cashflow-bank-statement"]["sheets"][0]["rows"]
        operations_rows = materials["production-operations"]["sheets"][0]["rows"]
        revenue_rows = materials["revenue-revenue-ledger"]["sheets"][0]["rows"]
        assert len(statement_rows) == len(operations_rows) == len(revenue_rows) == 75
        account = materials["cashflow-account-info"]["pages"][0]["lines"][1].split("：", 1)[1]
        assert {row[1] for row in statement_rows} == {account}
        assert materials["cashflow-operating-match"]["sheets"][0]["rows"][0][1] == account
        lease_pages = materials["transaction-lease-contract"]["pages"]
        rent_lines = [line for page in lease_pages[1:] for line in page["lines"]]
        assert len(rent_lines) == workbench["financedEquipment"]["repaymentSchedule"]["termMonths"]


def test_p5_originals_use_business_folders_and_derived_scene_is_not_a_material(bundles: tuple[dict, ...]) -> None:
    roots = {"基本证照", "经营证明", "现场照片", "增信", "租赁标的"}
    for bundle in bundles:
        workbench = bundle["workbench"]
        materials = workbench["materials"]
        material_by_id = {item["id"]: item for item in materials}
        assert {item["kind"] for item in materials} <= {"excel", "pdf", "image", "media"}
        assert not any(item["kind"] == "scene" for item in materials)
        assert not any(item["kind"] == "media" and item.get("mediaKind") == "panorama" for item in materials)
        assert all(item["folderPath"].split("/", 1)[0] in roots for item in materials)
        assert all(item["businessPath"] == f"{item['folderPath']}/{item['fileName']}" for item in materials)
        base_sheet_names = {item["name"] for item in materials[0]["sheets"]}
        assert not {"规则事实", "结构明细", "设备配置", "租金计划"} & base_sheet_names
        images = [item for item in materials if item["kind"] == "image"]
        assert len(images) == 21
        for item in images:
            assert (item["pixelWidth"], item["pixelHeight"]) == (2048, 1152)
            assert item.get("assetUrl") is None
        compliance_names = {
            item["fileName"] for item in materials if item["folderPath"].startswith("基本证照")
        }
        assert {"营业执照.png", "法定代表人身份证正面.png", "法定代表人身份证背面.png", "持证授权确认.png"} <= compliance_names
        line = workbench["financedEquipment"]["lines"][0]
        assert line["imageId"] in material_by_id
        assert all(material_by_id[item]["kind"] == "image" for item in line["imageIds"])
        assert material_by_id[line["nameplateMaterialId"]]["fileName"] == "设备铭牌.png"
        assert line["derivedModelRef"].startswith("derived-scene:")
        assert line["derivedModelRef"] not in material_by_id
        assert all(
            material_by_id[item["materialId"]]["kind"] == "image"
            for item in workbench["onsiteAssets"]
        )


def test_p5_compliance_and_reconciliation_facts_bind_to_their_business_originals(
    bundles: tuple[dict, ...],
) -> None:
    expected_categories = {
        "compliance.registration_valid": {"business-license", "registry-litigation"},
        "compliance.identity_consistency": {
            "identity-front",
            "identity-back",
            "authorization",
            "articles-equity",
        },
        "revenue.invoice_income_ratio": {"output-invoices", "income-statement"},
        "revenue.collection_invoice_ratio": {"collections", "output-invoices", "bank-statement"},
        "debt.total_debt": {"enterprise-credit", "personal-credit", "balance-sheet"},
        "cashflow.collection_cash_match": {"bank-statement", "collections"},
    }
    for bundle in bundles:
        workbench = bundle["workbench"]
        evidence_by_id = {item["id"]: item for item in workbench["evidence"]}
        for fact_key, categories in expected_categories.items():
            fact = next(item for item in workbench["facts"] if item["factKey"] == fact_key)
            located_material_ids = {
                evidence_by_id[ref]["locator"]["materialId"]
                for ref in fact["evidenceRefs"]
                if evidence_by_id[ref]["locator"] is not None
            }
            for category in categories:
                assert any(material_id.endswith(f"-{category}") for material_id in located_material_ids)
