"""LLM Integration for Cloud AI Trader using Google Gemini API.

Supports both official google-genai SDK and direct async HTTP REST requests
to ensure zero-breakage resilience across local, VPS, and container environments.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from config import settings

log = logging.getLogger("ai_trader.llm")

DECISION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "action": {"type": "STRING", "enum": ["BUY", "SELL", "NO_TRADE", "EXIT"]},
        "confidence": {"type": "NUMBER"},
        "regime": {"type": "STRING", "enum": ["trending_up", "trending_down", "ranging", "breakout", "high_volatility", "pre_news", "unclear"]},
        "setup": {"type": "STRING", "enum": ["pullback", "breakout", "none"]},
        "stop_atr": {"type": "NUMBER"},
        "target_r": {"type": "NUMBER"},
        "reason": {"type": "STRING"},
    },
    "required": ["action", "confidence", "regime", "setup", "stop_atr", "target_r", "reason"],
}


class LLMClient:
    """Async client communicating with Google Gemini models."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_retries = settings.LLM_MAX_RETRIES

    async def _call_gemini_rest(
        self,
        system_instruction: str,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Call Gemini REST API asynchronously using run_in_executor."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model or self.model}:generateContent"
        )

        contents: list[dict[str, Any]] = [
            {"role": "user", "parts": [{"text": prompt}]}
        ]

        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
            "responseMimeType": "application/json",
        }
        if response_schema:
            generation_config["responseSchema"] = response_schema
        if settings.LLM_THINKING_LEVEL:
            generation_config["thinkingConfig"] = {"thinkingLevel": settings.LLM_THINKING_LEVEL}

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": generation_config,
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        def _execute() -> str:
            with urlopen(req, timeout=timeout or settings.LLM_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError("Empty candidate content")
            return parts[0].get("text", "{}")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _execute)

    async def generate_json(
        self,
        system_instruction: str,
        user_content: str,
        response_schema: dict[str, Any] | None = None,
        default_fallback: dict[str, Any] | None = None,
        budget_s: float | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON within a time budget, then fail closed.

        Order: primary model, the lighter fallback model, then the primary again
        while time remains. Each attempt is capped by LLM_TIMEOUT_S and by the
        remaining budget so the EA always gets an answer before its own timeout.
        Failure is marked with "_llm_error" so callers can tell a real NO_TRADE
        from an unavailable model.
        """
        fallback = dict(default_fallback or {})
        if not self.api_key:
            log.warning("GEMINI_API_KEY is not set. Returning safe default.")
            return {**fallback, "_llm_error": "no_api_key"}

        attempts = [self.model]
        if settings.LLM_FALLBACK_MODEL and settings.LLM_FALLBACK_MODEL != self.model:
            attempts.append(settings.LLM_FALLBACK_MODEL)
        attempts += [self.model] * max(0, self.max_retries - 1)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget_s if budget_s else None
        last_error = "unknown"
        for attempt, model in enumerate(attempts, start=1):
            timeout = settings.LLM_TIMEOUT_S
            if deadline is not None:
                timeout = min(timeout, deadline - loop.time() - 0.2)
                if timeout < 1.0:
                    last_error = "time_budget"
                    break
            try:
                text_response = await self._call_gemini_rest(
                    system_instruction=system_instruction,
                    prompt=user_content,
                    response_schema=response_schema,
                    model=model,
                    timeout=timeout,
                )
                parsed = json.loads(text_response)
                if isinstance(parsed, dict):
                    parsed["_model"] = model
                    return parsed
                last_error = "non_dict_json"
                log.warning("LLM response was not a JSON dictionary: %s", text_response[:100])
            except Exception as exc:
                last_error = type(exc).__name__
                log.warning("LLM attempt %d (%s) failed: %s", attempt, model, exc)

        log.error("LLM unavailable after %d attempt(s): %s", attempt, last_error)
        return {**fallback, "_llm_error": last_error}

    async def make_decision(
        self,
        snapshot: dict[str, Any],
        market_context: dict[str, Any],
        system_prompt: str,
        decision_prompt: str,
        rules: str,
        prefs: str,
        recent_trades: list[dict[str, Any]],
        account_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Decide trade action given market context and self-maintained knowledge."""
        user_data = {
            "market_snapshot": snapshot,
            "market_context": market_context,
            "trading_rules": rules,
            "strategy_preferences": prefs,
            "recent_trades": recent_trades[:5],
            "account_state": account_state,
        }
        fallback = {
            "action": "NO_TRADE",
            "confidence": 0.0,
            "regime": market_context.get("regime", "unclear"),
            "setup": "none",
            "stop_atr": 1.5,
            "target_r": 1.5,
            "reason": "Fallback: safe fail-closed decision",
        }
        return await self.generate_json(
            system_instruction=f"{system_prompt}\n\n{decision_prompt}",
            user_content=json.dumps(user_data, ensure_ascii=False),
            default_fallback=fallback,
        )

    async def reflect_on_trade(
        self,
        trade_result: dict[str, Any],
        original_decision: dict[str, Any],
        system_prompt: str,
        reflection_prompt: str,
        rules: str,
    ) -> dict[str, Any]:
        """Reflect on completed trade outcome and extract learning points."""
        user_data = {
            "trade_result": trade_result,
            "original_decision": original_decision,
            "current_trading_rules": rules,
        }
        fallback = {
            "trade_assessment": "unlucky",
            "regime_was_correct": False,
            "entry_timing": "late",
            "sl_assessment": "appropriate",
            "tp_assessment": "appropriate",
            "key_lesson": "Automated fallback reflection recorded.",
            "suggested_rule_change": None,
            "suggested_param_change": None,
        }
        return await self.generate_json(
            system_instruction=f"{system_prompt}\n\n{reflection_prompt}",
            user_content=json.dumps(user_data, ensure_ascii=False),
            default_fallback=fallback,
        )

    async def daily_review(
        self,
        trades_today: list[dict[str, Any]],
        decisions_today: list[dict[str, Any]],
        system_prompt: str,
        daily_review_prompt: str,
        rules: str,
        prefs: str,
    ) -> dict[str, Any]:
        """Perform end-of-day trading review and propose knowledge improvements."""
        user_data = {
            "trades_today": trades_today,
            "decisions_today": decisions_today[-20:],
            "current_trading_rules": rules,
            "strategy_preferences": prefs,
        }
        fallback = {
            "summary": "No daily review generated (LLM unavailable)",
            "dominant_regime": "unclear",
            "regime_accuracy": "same",
            "patterns_identified": [],
            "missed_opportunities": [],
            "trades_to_avoid": [],
            "proposed_rule_changes": [],
            "proposed_param_changes": [],
        }
        return await self.generate_json(
            system_instruction=f"{system_prompt}\n\n{daily_review_prompt}",
            user_content=json.dumps(user_data, ensure_ascii=False),
            default_fallback=fallback,
        )
