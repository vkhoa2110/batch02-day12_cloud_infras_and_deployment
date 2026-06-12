from __future__ import annotations

import json
import os
from typing import Any

from codebase.chatbot_parser.openai_parser import (
    DEFAULT_OPENAI_MODEL,
    OpenAIParserError,
    _post_json,
)


class FinalAnswerError(RuntimeError):
    """Raised when the final LLM answer cannot be generated."""


FINAL_ANSWER_SYSTEM_PROMPT = """Bạn là chatbot gợi ý món ăn cho demo ShopeeFood Quận 1.

Nhiệm vụ:
- Trả lời tự nhiên bằng tiếng Việt, ngắn gọn, hữu ích.
- Chỉ dùng các món trong retrieved_data. Không tự bịa món, giá, quán, rating hoặc địa chỉ.
- Nếu người dùng yêu cầu gợi ý món ăn, chú ý kẻo nhầm lẫn việc đưa vào các món ăn không liên quan (ví dụ người dùng yêu cầu xôi mà xuất ra món giò chả của quán xôi cô ba chả hạn)
- Nếu strict items rỗng nhưng có near_misses hoặc fallback_items, nói rõ đây là gợi ý gần đúng.
- Nêu vì sao món phù hợp với yêu cầu: giá, giao nhanh, rating, cay/healthy/tag nếu có.
- Nếu có dị ứng hoặc ràng buộc "không ăn X", nhắc rằng kết quả đã lọc theo ràng buộc đó.
- Nếu không có dữ liệu phù hợp, hỏi lại một câu để thu hẹp hoặc nới điều kiện.
- Không in JSON trong câu trả lời cuối cùng.
"""


def generate_final_answer_with_gpt(
    user_message: str,
    task: dict[str, Any],
    retrieved_data: dict[str, Any],
    *,
    model: str | None = None,
    api_key: str | None = None,
    timeout_sec: int = 30,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    resolved_api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise FinalAnswerError("Missing OPENAI_API_KEY for final answer generation.")

    resolved_model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    payload = {
        "model": resolved_model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": FINAL_ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_message": user_message,
                        "conversation_history": _trim_history(conversation_history),
                        "parsed_task": _trim_task(task),
                        "retrieved_data": _trim_retrieval(retrieved_data),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    try:
        response = _post_json(
            "/chat/completions",
            payload,
            api_key=resolved_api_key,
            timeout_sec=timeout_sec,
        )
    except OpenAIParserError as exc:
        raise FinalAnswerError(str(exc)) from exc

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FinalAnswerError("OpenAI API response did not include final answer text.") from exc

    if not content or not str(content).strip():
        raise FinalAnswerError("OpenAI API returned an empty final answer.")
    return str(content).strip()


def build_template_answer(
    user_message: str,
    task: dict[str, Any],
    retrieved_data: dict[str, Any],
) -> str:
    """Offline final answer fallback for demos without a working API key."""

    if task.get("needs_clarification") or task.get("intent") == "unknown":
        questions = task.get("clarifying_questions") or [
            "Bạn muốn mình gợi ý theo giá, món cụ thể, độ cay, healthy hay giao nhanh?"
        ]
        return questions[0]

    items = retrieved_data.get("items") or []
    label = "Mình gợi ý vài món hợp yêu cầu:"
    if not items:
        items = retrieved_data.get("near_misses") or retrieved_data.get("fallback_items") or []
        label = "Mình chưa thấy món khớp hoàn toàn, nhưng có vài lựa chọn gần đúng:"

    if not items:
        return "Mình chưa tìm thấy món phù hợp trong mock data. Bạn muốn nới giá, đổi loại món hay bỏ bớt điều kiện nào?"

    lines = [label]
    for index, item in enumerate(items[:3], start=1):
        reasons = item.get("match_reasons") or []
        reason_text = f" ({'; '.join(reasons[:2])})" if reasons else ""
        lines.append(
            f"{index}. {item['item_name']} - {item['effective_price']:,}đ tại "
            f"{item['shop_name']}, rating {item['item_rating']}/5, giao khoảng "
            f"{item['avg_delivery_time_min']} phút{reason_text}."
        )

    if _has_restriction(task):
        lines.append("Mình đã ưu tiên lọc theo các ràng buộc bạn đưa ra trong task JSON.")

    return "\n".join(lines)


def _trim_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_text": task.get("source_text"),
        "task_type": task.get("task_type"),
        "intent": task.get("intent"),
        "primary_intent": task.get("primary_intent"),
        "sub_intents": task.get("sub_intents", []),
        "entities": task.get("entities", {}),
        "filters": task.get("filters", {}),
        "ranking": task.get("ranking", {}),
        "needs_clarification": task.get("needs_clarification", False),
        "clarifying_questions": task.get("clarifying_questions", []),
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


def _trim_retrieval(retrieved_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": [_trim_item(item) for item in (retrieved_data.get("items") or [])[:5]],
        "near_misses": [
            _trim_item(item) for item in (retrieved_data.get("near_misses") or [])[:3]
        ],
        "fallback_items": [
            _trim_item(item) for item in (retrieved_data.get("fallback_items") or [])[:5]
        ],
        "warnings": retrieved_data.get("warnings", []),
    }


def _trim_item(item: dict[str, Any]) -> dict[str, Any]:
    keep_keys = [
        "item_id",
        "item_name",
        "effective_price",
        "base_price",
        "item_rating",
        "item_sold_count",
        "spicy_level",
        "calories_estimate",
        "category_name",
        "shop_name",
        "shop_rating",
        "avg_delivery_time_min",
        "estimated_delivery_fee",
        "full_address",
        "recommendation_score",
        "tags",
        "allergens",
        "promotions",
        "match_reasons",
    ]
    return {key: item.get(key) for key in keep_keys if key in item}


def _has_restriction(task: dict[str, Any]) -> bool:
    entities = task.get("entities") or {}
    filters = task.get("filters") or {}
    return bool(
        entities.get("exclude_allergens")
        or entities.get("exclude_tags")
        or filters.get("max_effective_price")
        or filters.get("max_avg_delivery_time_min")
    )
