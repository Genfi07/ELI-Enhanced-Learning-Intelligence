from app.core.context_builder import ContextBuilder
from app.db.models.message import Message


class _Msg:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def test_system_prompt_always_included():
    ctx = ContextBuilder()
    messages = ctx.build([], "hola", max_tokens=200)
    assert messages[0].role == "system"
    assert "ELI" in messages[0].content


def test_budget_respected():
    ctx = ContextBuilder()
    history = [_Msg("user", "x" * 400) for _ in range(50)]  # ~100 tokens c/u
    messages = ctx.build(history, "consulta", max_tokens=2_000)
    total = sum(len(m.content) // 4 + 4 for m in messages)
    assert total <= 2_000


def test_oldest_dropped_first():
    ctx = ContextBuilder()
    history = [_Msg("user", f"msg-{i}-" + "x" * 200) for i in range(30)]
    messages = ctx.build(history, "última", max_tokens=1_500)
    # El último mensaje del historial debe estar presente; los primeros deben caerse.
    contents = " ".join(m.content for m in messages)
    assert "msg-29-" in contents
    assert "msg-0-" not in contents


def test_user_message_always_last():
    ctx = ContextBuilder()
    messages = ctx.build([_Msg("user", "previo")], "consulta actual", max_tokens=500)
    assert messages[-1].role == "user"
    assert messages[-1].content == "consulta actual"