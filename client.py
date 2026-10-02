"""OpenAI Chat Completions 도구 호출 루프 (FR-AI-01~06). 계산은 도구가, 해설은 모델이 맡는다."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from engine.models import TaxpayerInput

from .guard import GuardReport, check
from .prompts import CONFIRMED_MESSAGE, GUARD_RETRY_MESSAGE, SYSTEM_PROMPT
from .tools import ToolExecutor, openai_tools

logger = logging.getLogger("tax_agent")

DEFAULT_MODEL = "gpt-5.4-mini"
MAX_TOOL_ROUNDS = 8
GUARD_FAILED_TEXT = ("AI 해설의 금액이 계산 결과와 일치하지 않아 해설을 표시하지 않습니다. "
                     "위의 계산 결과 표와 계산 근거를 확인해 주세요.")
REFUSAL_TEXT = "이 요청에는 답변할 수 없습니다. 보유세 계산과 관련된 질문을 해 주세요."


class AgentUnavailable(RuntimeError):
    """API 키가 없거나 SDK를 쓸 수 없음."""


def _secret(name: str) -> str | None:
    """환경변수(.env 포함) → Streamlit secrets 순으로 조회."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        import streamlit as st
        return st.secrets.get(name) or None
    except Exception:
        return None


def api_key_available() -> bool:
    return bool(_secret("OPENAI_API_KEY"))


def configured_model() -> str:
    return _secret("OPENAI_MODEL") or DEFAULT_MODEL


@dataclass
class AgentReply:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    guard: GuardReport | None = None
    guard_retried: bool = False
    guard_failed: bool = False
    pending_input: TaxpayerInput | None = None
    error: str | None = None


class TaxAgent:
    """대화 이력과 도구 실행기를 가진 상담 에이전트."""

    def __init__(self, client: Any = None, model: str | None = None, executor: ToolExecutor | None = None):
        self._client = client
        self.model = model or configured_model()
        self.executor = executor or ToolExecutor()
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    @property
    def client(self) -> Any:
        if self._client is None:
            key = _secret("OPENAI_API_KEY")
            if not key:
                raise AgentUnavailable("OPENAI_API_KEY가 설정되지 않았습니다")
            from openai import OpenAI
            self._client = OpenAI(api_key=key)
        return self._client

    # ---- 공개 API ----
    def confirm_input(self, inp: TaxpayerInput) -> AgentReply:
        """사용자가 확인·수정한 입력을 확정하고 계산·해설을 요청한다."""
        self.executor.confirm(inp)
        return self.chat(CONFIRMED_MESSAGE)

    def chat(self, user_text: str) -> AgentReply:
        self.messages.append({"role": "user", "content": user_text})
        try:
            text, calls, stop = self._run_loop()
        except AgentUnavailable as e:
            self.messages.pop()
            return AgentReply(text="", error=str(e))
        except Exception as e:  # SDK 오류는 화면에 안내하고 앱은 계속 동작
            logger.exception("OpenAI API 호출 실패")
            return AgentReply(text="", error=f"AI 응답을 받지 못했습니다: {type(e).__name__}: {e}")

        reply = AgentReply(text=text, tool_calls=calls, pending_input=self.executor.pending_input)
        if stop == "refusal":
            reply.text = text or REFUSAL_TEXT
            return reply

        report = check(text, self.executor.known_numbers)
        if not report.ok:
            reply.guard_retried = True
            amounts = ", ".join(a.raw for a in report.mismatches)
            self.messages.append({"role": "user", "content": GUARD_RETRY_MESSAGE.format(amounts=amounts)})
            try:
                text, more_calls, stop = self._run_loop()
            except Exception as e:
                logger.exception("검증 재생성 실패")
                text, more_calls = "", []
                reply.error = f"재생성 실패: {e}"
            reply.tool_calls += more_calls
            report = check(text, self.executor.known_numbers)
            reply.text = text if report.ok else GUARD_FAILED_TEXT
            reply.guard_failed = not report.ok
        reply.guard = report
        reply.pending_input = self.executor.pending_input
        return reply

    # ---- 내부 ----
    def _create(self) -> Any:
        return self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=openai_tools(),
            tool_choice="auto",
        )

    def _run_loop(self) -> tuple[str, list[dict[str, Any]], str]:
        """도구 호출이 끝날 때까지 반복하고 (최종 텍스트, 도구 호출 기록, 종료 사유)를 반환."""
        calls: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ROUNDS):
            choice = self._create().choices[0]
            msg = choice.message
            tool_calls = list(getattr(msg, "tool_calls", None) or [])

            if getattr(msg, "refusal", None):
                self.messages.append({"role": "assistant", "content": msg.refusal})
                return msg.refusal, calls, "refusal"
            if choice.finish_reason == "content_filter":
                return "", calls, "refusal"

            assistant: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if tool_calls:
                assistant["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls]
            self.messages.append(assistant)

            if not tool_calls:
                text = (msg.content or "").strip()
                if choice.finish_reason == "length":
                    text += "\n\n(응답이 길어 중간에 잘렸습니다.)"
                return text, calls, choice.finish_reason or "stop"

            # 모든 도구 결과를 같은 순서로 돌려준다
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    output, is_error, args = json.dumps({"error": "도구 인자가 올바른 JSON이 아닙니다"},
                                                        ensure_ascii=False), True, {}
                else:
                    output, is_error = self.executor.execute(tc.function.name, args)
                calls.append({"name": tc.function.name, "input": args, "is_error": is_error})
                logger.info("tool %s error=%s", tc.function.name, is_error)
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})
        return "도구 호출 횟수가 너무 많아 응답을 마치지 못했습니다. 질문을 나눠서 해 주세요.", calls, "max_rounds"
