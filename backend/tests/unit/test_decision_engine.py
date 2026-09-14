import pytest

from app.core.decision_engine import DecisionEngine


@pytest.mark.parametrize(
    "message,expected_route",
    [
        ("¿Cuánto es 25 × 4?", "FAST"),
        ("Hola", "FAST"),
        ("¿Qué hora es?", "FAST"),
        ("Como te dije, prefiero explicaciones paso a paso", "STANDARD"),
        ("Según el documento que subí, resume los puntos clave", "STANDARD"),
        ("Analiza mi proyecto y dime cómo convertirlo en una plataforma comercial", "DEEP"),
        ("Diseña la arquitectura de un sistema de inventario", "DEEP"),
    ],
)
def test_route_classification(message, expected_route):
    plan = DecisionEngine().plan_for(message)
    assert plan.route == expected_route


def test_fast_skips_all_cognitive_modules():
    plan = DecisionEngine().plan_for("¿Cuánto es 25 × 4?")
    assert plan.route == "FAST"
    assert plan.needs_memory is False
    assert plan.needs_rag is False
    assert plan.needs_tools is False
    assert plan.needs_planning is False
    assert plan.needs_validation is False


def test_deep_enables_all_modules():
    plan = DecisionEngine().plan_for("Analiza mi proyecto completo y planifica los pasos")
    assert plan.route == "DEEP"
    assert plan.needs_planning is True
    assert plan.needs_validation is True
    assert plan.budget.max_tool_calls >= 1