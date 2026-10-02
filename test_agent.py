"""에이전트 도구 호출 흐름 (OpenAI 클라이언트 mock, 실제 API 호출 없음)."""
import json
from datetime import date
from types import SimpleNamespace

from agent.client import GUARD_FAILED_TEXT, TaxAgent
from agent.tools import ToolExecutor, openai_tools
from engine.models import House, TaxpayerInput


def text(t):
    """도구 호출 없이 텍스트만 있는 응답."""
    return SimpleNamespace(content=t, tool_calls=None, refusal=None)


def tool(name, args, id_="t1"):
    call = SimpleNamespace(id=id_, type="function", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    return SimpleNamespace(content=None, tool_calls=[call], refusal=None)


def resp(message=None, stop="stop"):
    message = message or SimpleNamespace(content="", tool_calls=None, refusal=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=stop)])


class FakeClient:
    """client.chat.completions.create 호출을 기록하고 준비된 응답을 차례로 돌려준다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


PARSE_ARGS = {"age": 66, "houses": [{"name": "서울 아파트", "official_price": "20억", "holding_years": 12}]}


def confirmed_input():
    return TaxpayerInput(birth_date=date(1960, 1, 1), houses=[
        House(name="서울 아파트", official_price=2_000_000_000, acquired_date=date(2014, 6, 1))])


def test_parse_flow_sets_pending_input(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    fake = FakeClient([
        resp(tool("parse_user_input", PARSE_ARGS), stop="tool_calls"),
        resp(text("입력 확인 카드에서 확인 후 [이 입력으로 계산]을 눌러 주세요.")),
    ])
    agent = TaxAgent(client=fake)
    reply = agent.chat("서울 아파트 1채, 공시가 20억, 12년 보유, 만 66세")
    assert reply.error is None
    assert reply.pending_input is not None
    assert reply.pending_input.houses[0].official_price == 2_000_000_000
    assert reply.pending_input.houses[0].acquired_date == date(2014, 6, 1)
    assert reply.pending_input.birth_date == date(1960, 1, 1)
    # 두 번째 호출에 도구 결과가 tool_call_id와 함께 전달됨
    sent = fake.calls[1]["messages"]
    assert sent[0]["role"] == "system"
    assert sent[-2]["role"] == "assistant" and sent[-2]["tool_calls"][0]["id"] == "t1"
    assert sent[-1]["role"] == "tool" and sent[-1]["tool_call_id"] == "t1"
    assert fake.calls[0]["model"] == "gpt-5.4-mini"
    assert fake.calls[0]["tools"] == openai_tools()


def test_one_house_household_defaults_to_auto():
    ex = ToolExecutor()
    base = {"age": 60, "houses": [{"name": "A", "official_price": "10억", "holding_years": 5}]}
    for value, expected in [(None, None), ("auto", None), ("yes", True), ("no", False)]:
        args = dict(base) if value is None else {**base, "one_house_household": value}
        ex.execute("parse_user_input", args)
        assert ex.pending_input.is_one_house_household is expected


def test_incomplete_parse_reports_missing():
    ex = ToolExecutor()
    out, is_error = ex.execute("parse_user_input", {"houses": [{"name": "A", "official_price": "10억"}]})
    data = json.loads(out)
    assert not is_error
    assert data["status"] == "incomplete"
    assert "생년월일 또는 만 나이" in data["missing_fields"]
    assert "A: 취득일 또는 보유기간" in data["missing_fields"]
    assert ex.pending_input is None


def test_calculation_requires_confirmation():
    out, is_error = ToolExecutor().execute("calculate_total", {})
    assert is_error and "확정" in json.loads(out)["error"]


def test_confirm_calculate_and_explain_passes_guard():
    fake = FakeClient([
        resp(tool("calculate_total", {}), stop="tool_calls"),
        resp(text("총 보유세는 5,506,560원(약 551만 원)입니다. 종부세 568,800원, 농특세 113,760원.")),
    ])
    agent = TaxAgent(client=fake)
    reply = agent.confirm_input(confirmed_input())
    assert reply.guard.ok
    assert not reply.guard_retried
    assert "5,506,560원" in reply.text
    assert reply.tool_calls == [{"name": "calculate_total", "input": {}, "is_error": False}]


def test_guard_retry_fixes_answer():
    fake = FakeClient([
        resp(tool("calculate_total", {}), stop="tool_calls"),
        resp(text("총 보유세는 5,600,000원입니다.")),
        resp(text("총 보유세는 5,506,560원입니다.")),
    ])
    agent = TaxAgent(client=fake)
    reply = agent.confirm_input(confirmed_input())
    assert reply.guard_retried and not reply.guard_failed
    assert reply.text == "총 보유세는 5,506,560원입니다."
    assert "[자동 검증]" in fake.calls[2]["messages"][-1]["content"]


def test_guard_failure_hides_explanation():
    fake = FakeClient([
        resp(tool("calculate_total", {}), stop="tool_calls"),
        resp(text("총 보유세는 5,600,000원입니다.")),
        resp(text("다시 계산하면 5,700,000원입니다.")),
    ])
    reply = TaxAgent(client=fake).confirm_input(confirmed_input())
    assert reply.guard_failed
    assert reply.text == GUARD_FAILED_TEXT


def test_scenario_tool():
    ex = ToolExecutor()
    ex.confirm(TaxpayerInput(birth_date=date(1970, 1, 1), houses=[
        House(name="A", official_price=1_000_000_000, acquired_date=date(2015, 1, 1)),
        House(name="B", official_price=700_000_000, acquired_date=date(2020, 1, 1))]))
    out, is_error = ex.execute("compare_scenarios", {"scenarios": [
        {"kind": "sell", "house_name": "B"},
        {"kind": "add_house", "house": {"name": "C", "official_price": "3억", "holding_years": 0}}]})
    data = json.loads(out)
    assert not is_error
    assert data["scenarios"][0]["comprehensive"] == 0
    assert abs(data["scenarios"][0]["diff_total"]) in ex.known_numbers  # 음수 차액은 절댓값으로 기록


def test_get_tax_rule():
    out, is_error = ToolExecutor().execute("get_tax_rule", {"key": "comprehensive_tax.deduction"})
    assert not is_error
    assert json.loads(out)["value"]["one_house"] == 1_200_000_000
    _, is_error = ToolExecutor().execute("get_tax_rule", {"key": "nope.x"})
    assert is_error


def test_unknown_tool_is_error():
    _, is_error = ToolExecutor().execute("hack", {})
    assert is_error


def test_no_api_key_is_graceful(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("agent.client._secret", lambda name: None)
    reply = TaxAgent().chat("안녕")
    assert reply.error and "OPENAI_API_KEY" in reply.error


def test_api_exception_is_graceful():
    class Boom:
        chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **k: (_ for _ in ()).throw(RuntimeError("down"))))

    reply = TaxAgent(client=Boom()).chat("안녕")
    assert reply.error and "down" in reply.error


def test_refusal_message():
    fake = FakeClient([resp(SimpleNamespace(content=None, tool_calls=None, refusal="거절합니다"))])
    reply = TaxAgent(client=fake).chat("...")
    assert reply.text == "거절합니다"
    fake = FakeClient([resp(stop="content_filter")])
    assert "답변할 수 없습니다" in TaxAgent(client=fake).chat("...").text


def test_invalid_tool_arguments_are_reported_as_error():
    bad = SimpleNamespace(id="x", type="function", function=SimpleNamespace(name="calculate_total", arguments="{bad"))
    fake = FakeClient([resp(SimpleNamespace(content=None, tool_calls=[bad], refusal=None), stop="tool_calls"),
                       resp(text("다시 시도할게요."))])
    reply = TaxAgent(client=fake).chat("계산해줘")
    assert reply.tool_calls[0]["is_error"]
    assert "JSON" in fake.calls[1]["messages"][-1]["content"]


def test_model_override_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.5")
    assert TaxAgent(client=FakeClient([])).model == "gpt-5.5"
