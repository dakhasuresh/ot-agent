"""
tests/test_pipeline.py
──────────────────────
Core pipeline tests — no LLM or ChromaDB required.
Tests the deterministic path and schema validation.

Run:
    pytest tests/ -v
"""

import asyncio
import pytest
from schemas import (
    AssetReport,
    BatchReport,
    ClassificationResult,
    ControlRecommendation,
    RiskScore,
)
from agent.tools import classify_asset, score_risk, generate_controls


# ── Fixtures ──────────────────────────────────────────────────────────────────

KNOWN_ASSETS = [
    {"device_type": "SIS",          "manufacturer": "Triconex",  "expected_zone": "Safety",        "expected_band": "Critical"},
    {"device_type": "PLC",          "manufacturer": "Siemens",   "expected_zone": "Critical OT",   "expected_band": "Critical"},
    {"device_type": "SCADA Server", "manufacturer": "AVEVA",     "expected_zone": "Critical OT",   "expected_band": "High"},
    {"device_type": "Historian",    "manufacturer": "OSIsoft",   "expected_zone": "General OT",    "expected_band": "High"},
    {"device_type": "Jump Server",  "manufacturer": None,        "expected_zone": "IT/OT Boundary","expected_band": "Medium"},
]


# ── Classification tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("asset", KNOWN_ASSETS)
async def test_deterministic_classification(asset):
    result = await classify_asset(
        device_type=asset["device_type"],
        manufacturer=asset.get("manufacturer"),
        llm=None,   # deterministic only
    )
    assert result.classification_path == "deterministic", (
        f"{asset['device_type']} should be deterministic — got {result.classification_path}"
    )
    assert result.confidence == 1.0
    assert result.iec62443_zone == asset["expected_zone"], (
        f"{asset['device_type']}: expected zone {asset['expected_zone']!r}, got {result.iec62443_zone!r}"
    )


@pytest.mark.asyncio
async def test_unmatched_without_llm():
    result = await classify_asset(device_type="Completely Unknown Gizmo XR9000", llm=None)
    assert result.classification_path == "unmatched"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classification_result_schema():
    result = await classify_asset(device_type="PLC", manufacturer="Rockwell", llm=None)
    assert isinstance(result, ClassificationResult)
    assert result.purdue_level in ("L0", "L1", "L2", "L3", "L3.5", "L4")
    assert 0.0 <= result.confidence <= 1.0


# ── Risk scoring tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("asset", KNOWN_ASSETS)
async def test_risk_band(asset):
    classification = await classify_asset(
        device_type=asset["device_type"],
        manufacturer=asset.get("manufacturer"),
        llm=None,
    )
    risk = score_risk(classification)
    assert risk.risk_band == asset["expected_band"], (
        f"{asset['device_type']}: expected band {asset['expected_band']!r}, got {risk.risk_band!r}"
    )


@pytest.mark.asyncio
async def test_risk_score_range():
    classification = await classify_asset(device_type="PLC", llm=None)
    risk = score_risk(classification)
    assert isinstance(risk, RiskScore)
    assert 0 <= risk.risk_score <= 125
    assert 1 <= risk.threat_score <= 5
    assert 1 <= risk.vulnerability_score <= 5
    assert 1 <= risk.impact_score <= 5
    assert risk.risk_band in ("Critical", "High", "Medium", "Low")


@pytest.mark.asyncio
async def test_threat_patterns_present():
    classification = await classify_asset(device_type="SIS", llm=None)
    risk = score_risk(classification)
    assert len(risk.applicable_threat_patterns) > 0


# ── Control generation tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_controls_generated_without_llm():
    """Tiers 1 + 2 must fire even with no LLM or RAG."""
    classification = await classify_asset(device_type="PLC", llm=None)
    risk = score_risk(classification)
    controls = await generate_controls(
        classification=classification,
        risk=risk,
        store=None,
        llm=None,
    )
    assert len(controls) > 0
    # All from static tiers
    for c in controls:
        assert c.source in ("zone_static", "category_static")


@pytest.mark.asyncio
async def test_controls_schema():
    classification = await classify_asset(device_type="HMI", llm=None)
    risk = score_risk(classification)
    controls = await generate_controls(classification, risk, store=None, llm=None)

    for ctrl in controls:
        assert isinstance(ctrl, ControlRecommendation)
        assert ctrl.clause.startswith("IEC 62443")
        assert len(ctrl.text) > 10
        assert ctrl.priority in (1, 2, 3)
        assert ctrl.source in ("zone_static", "category_static", "llm_contextual")


@pytest.mark.asyncio
async def test_controls_sorted_by_priority():
    classification = await classify_asset(device_type="SIS", llm=None)
    risk = score_risk(classification)
    controls = await generate_controls(classification, risk, store=None, llm=None)
    priorities = [c.priority for c in controls]
    assert priorities == sorted(priorities), "Controls should be sorted priority 1 → 3"


@pytest.mark.asyncio
async def test_no_duplicate_clauses():
    classification = await classify_asset(device_type="PLC", llm=None)
    risk = score_risk(classification)
    controls = await generate_controls(classification, risk, store=None, llm=None)
    clause_keys = [c.clause.split(":")[0].strip() for c in controls]
    assert len(clause_keys) == len(set(clause_keys)), "Duplicate clause references in output"


# ── Batch report schema test ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_report_counts():
    from agent.orchestrator import OTAgentOrchestrator
    orch = OTAgentOrchestrator(enable_rag=False)
    batch = await orch.process_batch([
        {"device_type": "SIS"},
        {"device_type": "PLC", "manufacturer": "Siemens"},
        {"device_type": "Unknown Gizmo XR9000"},
    ])
    assert isinstance(batch, BatchReport)
    assert batch.total == 3
    assert batch.deterministic >= 2
    assert batch.deterministic + batch.llm_classified + batch.unmatched == batch.total
