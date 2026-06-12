"""Adapter for the Day06 ShopeeFood recommendation agent."""
from __future__ import annotations

import os
from typing import Any

from app.config import settings
from codebase.food_chatbot.answerer import FinalAnswerError
from codebase.food_chatbot.pipeline import run_food_chatbot
from codebase.chatbot_parser.openai_parser import OpenAIParserError


def run_shopee_food_agent(
    question: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the Day06 food chatbot with API mode when a key exists, else offline mode."""
    use_openai = bool(settings.openai_api_key)
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.llm_model:
        os.environ["OPENAI_MODEL"] = settings.llm_model

    try:
        result = run_food_chatbot(
            question,
            parse_mode="api" if use_openai else "rules",
            answer_mode="api" if use_openai else "template",
            model=settings.llm_model,
            fallback_rules=True,
            fallback_template=True,
            conversation_history=conversation_history or [],
        )
    except (OpenAIParserError, FinalAnswerError):
        result = run_food_chatbot(
            question,
            parse_mode="rules",
            answer_mode="template",
            model=settings.llm_model,
            conversation_history=conversation_history or [],
        )

    task = result["task"]
    retrieved_data = result["retrieved_data"]
    return {
        "answer": result["answer"],
        "intent": task,
        "recommendations": _to_recommendations(retrieved_data),
        "warnings": [str(warning) for warning in retrieved_data.get("warnings", [])],
        "mode": "openai" if use_openai else "offline",
    }


def _to_recommendations(retrieved_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (
        retrieved_data.get("items")
        or retrieved_data.get("near_misses")
        or retrieved_data.get("fallback_items")
        or []
    )
    return [_to_recommendation(row) for row in rows[:3]]


def _to_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    effective_price = _to_int(row.get("effective_price"))
    delivery_fee = _to_int(row.get("estimated_delivery_fee"))
    return {
        "item_id": str(row.get("item_id", "")),
        "item_name": str(row.get("item_name", "")),
        "shop_name": str(row.get("shop_name", "")),
        "category_name": str(row.get("category_name", "")),
        "effective_price": effective_price,
        "delivery_fee": delivery_fee,
        "total_price": effective_price + delivery_fee,
        "delivery_time_min": _to_int(row.get("avg_delivery_time_min")),
        "item_rating": _to_float(row.get("item_rating")),
        "shop_rating": _to_float(row.get("shop_rating")),
        "spicy_level": _to_int(row.get("spicy_level")),
        "score": _to_float(row.get("recommendation_score")),
        "reasons": [str(reason) for reason in row.get("match_reasons", [])],
    }


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)
