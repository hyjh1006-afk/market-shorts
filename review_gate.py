# -*- coding: utf-8 -*-
"""감독관 게이트 — 렌더 직전 내레이션 검수 (threads-kitchen 게이트와 동일 사상, 2026-07-27).

원칙 (Lee_dogin 파이프라인 이식):
- 검증은 텍스트 우선, 렌더는 최종만 → 장면(scenes)이 확정된 직후·렌더 전에 검수
- 하드 룰은 fail-closed, LLM 판정은 fail-open (검수 장애가 라이브 파이프라인을 멈추면 안 됨)
- 심각한 문제만 차단: 투자 조언 단정(매수·매도 권유), 혐오, 깨진 텍스트, 명백한 허위
- 스타일 지적은 logs/review_log.md에 경고로만 축적
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
RULES_PATH = BASE / "review_rules.md"
LOG_PATH = BASE / "logs" / "review_log.md"


def _hard_check(full_text: str) -> list[str]:
    bad = []
    if not full_text.strip():
        bad.append("내레이션이 비어 있음")
    if "�" in full_text:
        bad.append("깨진 문자(인코딩 오류) 포함")
    if "{" in full_text and "}" in full_text:
        bad.append("템플릿 변수 흔적({...}) 노출")
    if len(full_text) > 4000:
        bad.append(f"내레이션 비정상 길이 ({len(full_text)}자)")
    return bad


def _llm_review(full_text: str) -> tuple[bool, list[str]]:
    """(차단 여부, 경고들). LLM 불가 시 통과 (fail-open)."""
    rules = RULES_PATH.read_text(encoding="utf-8") if RULES_PATH.exists() else ""
    prompt = f"""너는 한국어 주식·경제 유튜브 쇼츠의 내레이션 검수 감독관이다.
JSON으로만 답하라: {{"block": true/false, "warnings": ["..."]}}

block=true 는 오직 심각한 문제일 때만:
- 특정 종목의 매수·매도를 단정적으로 권유 (투자 조언 — 법적 리스크)
- "무조건 오른다" 같은 수익 보장 표현
- 혐오·비하 표현
- 깨진 문장, 템플릿 변수 노출
- 데이터와 명백히 모순되는 서술

말투·재미 등 스타일 의견은 warnings로. warnings 최대 3개, 각 한 문장.

{rules}

[내레이션 전문]
{full_text}"""
    try:
        from generators import llm_gen
        if not llm_gen.is_available():
            return False, ["(검수 LLM 키 없음 — 통과)"]
        content = llm_gen._call(prompt)
        start, end = content.find("{"), content.rfind("}")
        verdict = json.loads(content[start:end + 1])
        return bool(verdict.get("block")), [str(w) for w in verdict.get("warnings", [])][:3]
    except Exception as e:
        return False, [f"(검수 LLM 불가 — 통과: {str(e)[:80]})"]


def _log(blocked: bool, hard: list[str], warnings: list[str]):
    try:
        LOG_PATH.parent.mkdir(exist_ok=True)
        lines = [f"## {date.today().isoformat()} — {'차단' if blocked else '통과'}"]
        lines += [f"- 하드 룰: {v}" for v in hard]
        lines += [f"- 경고: {w}" for w in warnings]
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except Exception:
        pass  # 로그 실패가 파이프라인을 막으면 안 됨


def gate(scenes: list[dict]) -> tuple[bool, str]:
    """렌더 허가 여부. scenes의 narration을 합쳐 검수한다."""
    full_text = "\n".join(s.get("narration", "") for s in scenes)
    hard = _hard_check(full_text)
    if hard:
        _log(True, hard, [])
        return False, "하드 룰 위반: " + " / ".join(hard)
    block, warnings = _llm_review(full_text)
    _log(block, [], warnings)
    if block:
        return False, "LLM 감독관 차단: " + " / ".join(warnings)
    return True, ("경고 " + str(len(warnings)) + "건 (로그)") if warnings else "이상 없음"
