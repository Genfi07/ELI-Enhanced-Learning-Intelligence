"""Tool: calculadora segura.

Evalúa expresiones matemáticas usando un evaluador basado en `ast` con
operadores whitelisted. NUNCA usa `eval()` ni `exec()`.

Soporta:
  - Operadores: + - * / // % ** y unarios + -
  - Funciones: abs, round, min, max, sum, pow
  - Constantes: pi, e
  - Paréntesis

Rechaza:
  - Atributos (a.b)
  - Subscript (a[b])
  - Llamadas que no estén en la whitelist
  - Comprehensions, lambdas, condicionales anidados
  - Cualquier nombre que no sea función/constante conocida

Nivel de autonomía mínimo: 2 (herramientas internas).
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any

from app.core.contracts.tool import ToolContext, ToolExecutionError
from app.core.schemas.tool import ToolManifest

# Operadores permitidos
_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
# Funciones permitidas
_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "int": int,
    "float": float,
}
# Constantes
_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

# Límites defensivos
_MAX_EXPRESSION_LEN = 500
_MAX_POWER = 1000  # para evitar 9**9**9 que revienta
_MAX_ABS_RESULT = 1e15


class CalculatorTool:
    manifest = ToolManifest(
        name="calculator",
        description=(
            "Evalúa expresiones matemáticas. Soporta +, -, *, /, //, %, **, "
            "paréntesis, y funciones como abs, round, min, max, sum, pow. "
            "Constantes: pi, e, tau."
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Expresión matemática a evaluar",
                }
            },
            "required": ["expression"],
        },
        required_permissions=[],
        min_autonomy_level=2,
        requires_confirmation=False,
        timeout_ms=2_000,
        enabled=True,
        scope="builtin",
    )

    async def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        expression = arguments.get("expression")
        if not isinstance(expression, str):
            raise ToolExecutionError("se requiere 'expression' como string")

        expression = expression.strip()
        if not expression:
            raise ToolExecutionError("expresión vacía")
        if len(expression) > _MAX_EXPRESSION_LEN:
            raise ToolExecutionError(
                f"expresión excede {_MAX_EXPRESSION_LEN} caracteres"
            )

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ToolExecutionError(f"sintaxis inválida: {exc.msg}") from exc

        try:
            result = self._eval(tree.body)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"error al evaluar: {exc}") from exc

        if isinstance(result, complex):
            raise ToolExecutionError("no se soportan números complejos")
        if abs(result) > _MAX_ABS_RESULT:
            raise ToolExecutionError("resultado fuera de rango permitido")

        return {
            "expression": expression,
            "result": result,
        }

    # ------------------------------------------------------------------ #
    # Evaluador
    # ------------------------------------------------------------------ #
    def _eval(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                raise ToolExecutionError("booleanos no permitidos")
            if isinstance(node.value, (int, float)):
                return node.value
            raise ToolExecutionError(
                f"constante no permitida: {type(node.value).__name__}"
            )

        if isinstance(node, ast.Name):
            if node.id in _CONSTANTS:
                return _CONSTANTS[node.id]
            if node.id in _FUNCTIONS:
                # Un nombre de función sin llamada no tiene sentido aquí
                raise ToolExecutionError(
                    f"'{node.id}' es una función; úsala con paréntesis"
                )
            raise ToolExecutionError(f"nombre no permitido: {node.id}")

        if isinstance(node, ast.BinOp):
            op = _BINARY_OPS.get(type(node.op))
            if op is None:
                raise ToolExecutionError(
                    f"operador no permitido: {type(node.op).__name__}"
                )
            left = self._eval(node.left)
            right = self._eval(node.right)
            # Protección específica para **
            if isinstance(node.op, ast.Pow):
                if isinstance(right, (int, float)) and abs(right) > _MAX_POWER:
                    raise ToolExecutionError(
                        f"exponente excede {_MAX_POWER}"
                    )
            return op(left, right)

        if isinstance(node, ast.UnaryOp):
            op = _UNARY_OPS.get(type(node.op))
            if op is None:
                raise ToolExecutionError(
                    f"operador unario no permitido: {type(node.op).__name__}"
                )
            return op(self._eval(node.operand))

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ToolExecutionError(
                    "solo se permiten llamadas a funciones por nombre"
                )
            fname = node.func.id
            fn = _FUNCTIONS.get(fname)
            if fn is None:
                raise ToolExecutionError(f"función no permitida: {fname}")
            if node.keywords:
                raise ToolExecutionError("argumentos con nombre no permitidos")
            args = [self._eval(a) for a in node.args]
            return fn(*args)

        raise ToolExecutionError(
            f"construcción no permitida: {type(node).__name__}"
        )