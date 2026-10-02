"""Claude API Tool Use 루프 (FR-AI-01~06). 계산은 도구가, 해설은 Claude가 맡는다."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from engine.models import TaxpayerInput

from .guard import GuardReport, check
from .prompts import CONFIRMED_MESSAGE, GUARD_RETRY_MESSAGE, SYSTEM_PROMPT
from .tools import TOOLS, ToolExecutor

logger = logging.getLogger("tax_agent")

MODEL = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOOL_ROUNDS = 8
GUARD_FAILED_TEXT = ("AI 해설의 금액이 계산 결과와 일치하지 않아 해설을 표시하지 않습니다. "
                     "위의 계산 결과 표와 계산 근거를 확인해 주세요.")


class AgentUnavailable(RuntimeError):
    """API 키가 없거나 SDK를 쓸 수 없음."""


def api_key_available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        import streamlit as st
        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:
        return False


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

    def __init__(self, client: Any = None, model: str = MODEL, executor: ToolExecutor | None = None):
        self._client = client
        self.model = model
        self.executor = executor or ToolExecutor()
        self.messages: list[dict[str, Any]] = []

    @property
    def client(self) -> Any:
        if self._client is None:
            if not api_key_available():
                raise AgentUnavailable("ANTHROPIC_API_KEY가 설정되지 않았습니다")
            import anthropic
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                import streamlit as st
                key = st.secrets["ANTHROPIC_API_KEY"]
            self._client = anthropic.Anthropic(api_key=key)
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
            logger.exception("Claude API 호출 실패")
            return AgentReply(text="", error=f"AI 응답을 받지 못했습니다: {type(e).__name__}: {e}")

        reply = AgentReply(text=text, tool_calls=calls, pending_input=self.executor.pending_input)
        if stop == "refusal":
            reply.text = text or "이 요청에는 답변할 수 없습니다. 보유세 계산과 관련된 질문을 해 주세요."
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
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self.messages,
            output_config={"effort": "medium"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    def _run_loop(self) -> tuple[str, list[dict[str, Any]], str]:
        """도구 호출이 끝날 때까지 반복하고 (최종 텍스트, 도구 호출 기록, stop_reason)을 반환."""
        calls: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create()
            # 응답 블록(thinking·fallback 포함)을 그대로 이력에 보존
            self.messages.append({"role": "assistant", "content": response.content})
            stop = response.stop_reason
            if stop == "pause_turn":
                continue
            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if stop != "tool_use" or not tool_uses:
                text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
                if stop == "max_tokens":
                    text += "\n\n(응답이 길어 중간에 잘렸습니다.)"
                return text, calls, stop
            results = []
            for block in tool_uses:
                output, is_error = self.executor.execute(block.name, block.input)
                calls.append({"name": block.name, "input": block.input, "is_error": is_error})
                logger.info("tool %s error=%s", block.name, is_error)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output,
                                **({"is_error": True} if is_error else {})})
            self.messages.append({"role": "user", "content": results})
        return "도구 호출 횟수가 너무 많아 응답을 마치지 못했습니다. 질문을 나눠서 해 주세요.", calls, "max_rounds"
