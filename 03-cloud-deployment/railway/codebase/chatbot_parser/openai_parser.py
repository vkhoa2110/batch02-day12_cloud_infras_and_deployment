from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .parser import DEFAULT_DATA_DIR, _load_vocab


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OPENAI_API_BASE = "https://api.openai.com/v1"


class OpenAIParserError(RuntimeError):
    """Raised when the GPT parser cannot return a usable task JSON."""


INTENT_VALUES = [
    "recommendation",
    "budget_meal",
    "healthy_food",
    "spicy_food",
    "fast_delivery",
    "vegetarian",
    "avoid_allergen",
    "group_order",
    "breakfast",
    "lunch",
    "dinner",
    "late_night",
    "snack",
    "specific_item_search",
    "unknown",
]

RANKING_FIELDS = [
    "recommendation_score",
    "item_rating",
    "effective_price",
    "avg_delivery_time_min",
    "item_sold_count",
    "shop_rating",
    "calories_estimate",
]

FILTER_FIELDS = [
    "is_available",
    "shop_status",
    "max_effective_price",
    "min_effective_price",
    "max_estimated_delivery_fee",
    "min_spicy_level",
    "max_spicy_level",
    "max_calories_estimate",
    "max_avg_delivery_time_min",
    "min_portion_people",
    "requires_discount",
]


TASK_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "version",
        "source_text",
        "task_type",
        "intent",
        "primary_intent",
        "sub_intents",
        "entities",
        "filters",
        "ranking",
        "limit",
        "confidence",
        "needs_clarification",
        "clarifying_questions",
    ],
    "properties": {
        "version": {"type": "string", "enum": ["food_task.v1"]},
        "source_text": {"type": "string"},
        "task_type": {
            "type": "string",
            "enum": [
                "recommend_items",
                "search_or_recommend_items",
                "clarify_food_need",
            ],
        },
        "intent": {"type": "string", "enum": ["recommend_items", "unknown"]},
        "primary_intent": {"type": "string", "enum": INTENT_VALUES},
        "sub_intents": {
            "type": "array",
            "items": {"type": "string", "enum": INTENT_VALUES},
        },
        "entities": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "include_tags",
                "exclude_tags",
                "include_cuisines",
                "dish_keywords",
                "exclude_allergens",
                "exclude_item_ids",
                "party_size",
            ],
            "properties": {
                "include_tags": {"type": "array", "items": {"type": "string"}},
                "exclude_tags": {"type": "array", "items": {"type": "string"}},
                "include_cuisines": {"type": "array", "items": {"type": "string"}},
                "dish_keywords": {"type": "array", "items": {"type": "string"}},
                "exclude_allergens": {"type": "array", "items": {"type": "string"}},
                "exclude_item_ids": {"type": "array", "items": {"type": "string"}},
                "party_size": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"},
                    ]
                },
            },
        },
        "filters": {
            "type": "object",
            "additionalProperties": False,
            "required": FILTER_FIELDS,
            "properties": {
                "is_available": {
                    "anyOf": [
                        {"type": "integer", "enum": [0, 1]},
                        {"type": "null"},
                    ]
                },
                "shop_status": {
                    "anyOf": [
                        {"type": "string", "enum": ["open", "closed", "busy"]},
                        {"type": "null"},
                    ]
                },
                "max_effective_price": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                },
                "min_effective_price": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                },
                "max_estimated_delivery_fee": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                },
                "min_spicy_level": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"},
                    ]
                },
                "max_spicy_level": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"},
                    ]
                },
                "max_calories_estimate": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                },
                "max_avg_delivery_time_min": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                },
                "min_portion_people": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"},
                    ]
                },
                "requires_discount": {
                    "anyOf": [{"type": "boolean"}, {"type": "null"}]
                },
            },
        },
        "ranking": {
            "type": "object",
            "additionalProperties": False,
            "required": RANKING_FIELDS,
            "properties": {
                field: {"type": "string", "enum": ["asc", "desc", "none"]}
                for field in RANKING_FIELDS
            },
        },
        "limit": {"type": "integer"},
        "confidence": {"type": "number"},
        "needs_clarification": {"type": "boolean"},
        "clarifying_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


SYSTEM_PROMPT = """You are the NLU parser for a ShopeeFood-style demo app in Ho Chi Minh City District 1.

Convert the Vietnamese user message into a machine-readable JSON task for food recommendation.

Important rules:
- Return only data that fits the provided JSON schema.
- Use VND integer amounts. "50k", "50 nghìn", "50 ngàn" all mean 50000.
- If the user asks for cheap, student, budget, or "dưới/tầm/không quá X", set max_effective_price.
- If the user asks "trên/hơn/từ X", set min_effective_price.
- For normal recommendation/search tasks, set is_available=1 and shop_status="open".
- Use dish_keywords for exact food names, for example "Bánh khọt Vũng Tàu".
- Use exclude_allergens for allergies or "không/tránh/đừng có" food restrictions.
- Use include_tags for taste, occasion, diet, promotion, and delivery hints.
- Use include_cuisines only when the message clearly names a cuisine in the catalog.
- Use max_avg_delivery_time_min for fast-delivery requests. Default fast delivery threshold is 20 minutes.
- Use min_spicy_level=3 for "cay cay", min_spicy_level=4 for "rất/siêu cay", and max_spicy_level=0 for "không cay".
- If the user asks for group ordering, set party_size and min_portion_people when possible.
- Use conversation_history for follow-up context. If the user says they disliked previous suggestions or asks for another option, keep the previous food constraints and put previous recommendation item IDs in entities.exclude_item_ids.
- Choose primary_intent as the strongest user need; put other matched needs in sub_intents.
- If the message is too vague or unrelated to food ordering, set task_type="clarify_food_need", intent="unknown", primary_intent="unknown", and add a short Vietnamese clarifying question.
"""


def parse_user_query_with_gpt(
    message: str,
    data_dir: str | Path | None = None,
    *,
    model: str | None = None,
    api_key: str | None = None,
    timeout_sec: int = 30,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a user query by calling GPT-4o mini with Structured Outputs."""

    resolved_api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise OpenAIParserError(
            "Missing OPENAI_API_KEY. Set it in the environment or run CLI with --mode rules."
        )

    resolved_model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    resolved_data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    catalog_context = build_catalog_context(resolved_data_dir)

    payload = {
        "model": resolved_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_message": message,
                        "conversation_history": _trim_history(conversation_history),
                        "catalog_context": catalog_context,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "food_recommendation_task",
                "strict": True,
                "schema": TASK_JSON_SCHEMA,
            },
        },
    }

    response = _post_json(
        "/chat/completions",
        payload,
        api_key=resolved_api_key,
        timeout_sec=timeout_sec,
    )
    task = _extract_task_from_response(response)
    return _compact_task(task, message, resolved_model)


def build_catalog_context(data_dir: Path) -> dict[str, Any]:
    vocab = _load_vocab(data_dir)

    return {
        "available_tags": _names(vocab["tags"]),
        "available_cuisines": _names(vocab["cuisines"]),
        "available_allergens": _names(vocab["allergens"]),
        "known_menu_items": _names(vocab["menu_items"]),
        "supported_filter_fields": FILTER_FIELDS,
        "supported_ranking_fields": RANKING_FIELDS,
        "default_filters": {"is_available": 1, "shop_status": "open"},
    }


def _trim_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not history:
        return []

    trimmed: list[dict[str, Any]] = []
    for message in history[-10:]:
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        item_ids = message.get("recommendation_item_ids") or []
        trimmed.append(
            {
                "role": role,
                "content": content[:1200],
                "recommendation_item_ids": [
                    str(item_id) for item_id in item_ids if str(item_id).strip()
                ][:8],
            }
        )
    return trimmed


def _names(rows: list[dict[str, str]]) -> list[str]:
    names = sorted({row["name"] for row in rows if row.get("name")})
    return names


def _post_json(
    path: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_sec: int,
) -> dict[str, Any]:
    api_base = os.getenv("OPENAI_API_BASE", OPENAI_API_BASE).rstrip("/")
    request = urllib.request.Request(
        f"{api_base}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIParserError(
            f"OpenAI API returned HTTP {exc.code}: {_sanitize_api_error(body)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OpenAIParserError(f"Cannot reach OpenAI API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OpenAIParserError("OpenAI API returned invalid JSON.") from exc


def _extract_task_from_response(response: dict[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIParserError("OpenAI API response did not include a chat message.") from exc

    refusal = message.get("refusal")
    if refusal:
        raise OpenAIParserError(f"OpenAI model refused the parsing request: {refusal}")

    content = message.get("content")
    if not content:
        raise OpenAIParserError("OpenAI API response message had no content.")

    try:
        task = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OpenAIParserError("OpenAI model output was not valid JSON.") from exc

    if not isinstance(task, dict):
        raise OpenAIParserError("OpenAI model output was not a JSON object.")
    return task


def _sanitize_api_error(body: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_\-*]+", "sk-***", body)


def _compact_task(task: dict[str, Any], source_text: str, model: str) -> dict[str, Any]:
    task["source_text"] = source_text
    task["model"] = model
    task["parser"] = "openai_chat_completions_json_schema"

    filters = task.get("filters") or {}
    task["filters"] = {
        key: value
        for key, value in filters.items()
        if value is not None and value != "none"
    }

    ranking = task.get("ranking") or {}
    task["ranking"] = {
        key: value
        for key, value in ranking.items()
        if value is not None and value != "none"
    }

    entities = task.get("entities") or {}
    compact_entities: dict[str, Any] = {}
    for key, value in entities.items():
        if value in (None, [], {}, "none"):
            continue
        compact_entities[key] = value
    task["entities"] = compact_entities

    if task.get("primary_intent") == "unknown":
        task["intent"] = "unknown"
        task["task_type"] = "clarify_food_need"
    elif task.get("entities", {}).get("dish_keywords"):
        task["task_type"] = "search_or_recommend_items"
        task["intent"] = "recommend_items"
    else:
        task["task_type"] = task.get("task_type") or "recommend_items"
        task["intent"] = "recommend_items"

    task.setdefault("version", "food_task.v1")
    task["limit"] = _clamp_int(task.get("limit", 10), minimum=1, maximum=20, default=10)
    task["confidence"] = _clamp_float(
        task.get("confidence", 0.0), minimum=0.0, maximum=1.0, default=0.0
    )
    task.setdefault("needs_clarification", False)
    task.setdefault("clarifying_questions", [])
    return task


def _clamp_int(value: Any, *, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _clamp_float(value: Any, *, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))
