"""The MCP server module imports, registers every tool and hands the safety rules to clients."""
import asyncio

from mcp_server.server import mcp
from mcp_server.tools import medication_safety


def test_server_registers_all_tools():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert len(names) == 28
    assert {"get_health_summary", "stage_lab_panel", "approve_staged_source", "log_meal",
            "check_medication_safety", "crisis_resources"} <= names


def test_safety_rules_reach_the_client():
    # sent in the initialize response → clients put them into the model's context
    assert "crisis_resources" in mcp.instructions
    assert "check_medication_safety" in mcp.instructions
    prompts = {p.name for p in asyncio.run(mcp.list_prompts())}
    assert "health_assistant" in prompts


def test_medication_safety_always_refuses_interactions():
    out = medication_safety([])
    assert "don't assess drug interactions" in out["interactions"]
    assert "paracetamol" not in out and "biotin" not in out


def test_medication_safety_sums_paracetamol_from_current_meds():
    meds = [{"medication_name": "Paracetamol", "dose_amount": 1000, "dose_unit": "mg",
             "times_per_day": 3},
            {"medication_name": "Ibuprofen", "dose_amount": 400, "dose_unit": "mg",
             "times_per_day": 2}]
    p = medication_safety(meds)["paracetamol"]
    assert p["total_mg_per_day"] == 3000 and p["level"] == "caution"
    assert p["source"] == "current_medications" and "Combination products" in p["note"]


def test_medication_safety_explicit_products_across_otc():
    products = [{"name": "Paracetamol", "mg_per_dose": 1000, "doses_per_day": 3},
                {"name": "Cold & flu powder", "mg_per_dose": 500, "doses_per_day": 3}]
    p = medication_safety([], paracetamol_products=products)["paracetamol"]
    assert p["level"] == "exceeded" and p["source"] == "provided"


def test_medication_safety_detects_biotin_from_meds():
    meds = [{"medication_name": "Biotin 5000 mcg", "dose_amount": 5000, "dose_unit": "mcg",
             "times_per_day": 1}]
    assert "tsh" in medication_safety(meds, planned_tests=["tsh"])["biotin"]
    assert "biotin" not in medication_safety(meds, planned_tests=["glucose"])


def test_every_tool_is_annotated_for_client_permissions():
    tools = {t.name: t.annotations for t in asyncio.run(mcp.list_tools())}
    assert all(a is not None for a in tools.values())
    writes = {n for n, a in tools.items() if not a.read_only_hint}
    assert writes == {"set_profile", "record_allergy", "record_diagnosis", "record_medication",
                      "log_meal", "save_meal_template", "log_from_template", "stage_lab_panel",
                      "approve_staged_source"}
    # approving turns unverified values into facts → clients should always confirm
    assert tools["approve_staged_source"].destructive_hint is True
    assert tools["crisis_resources"].read_only_hint and tools["sql_query"].read_only_hint
