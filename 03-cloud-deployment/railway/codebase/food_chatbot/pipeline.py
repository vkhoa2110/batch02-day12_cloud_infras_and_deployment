from __future__ import annotations

import unicodedata
from typing import Any

from codebase.chatbot_parser.openai_parser import OpenAIParserError, parse_user_query_with_gpt
from codebase.chatbot_parser.parser import parse_user_query

from .answerer import FinalAnswerError, build_template_answer, generate_final_answer_with_gpt
from .retriever import retrieve_items_for_task


def run_food_chatbot(
    user_message: str,
    *,
    task: dict[str, Any] | None = None,
    data_dir: str | None = None,
    parse_mode: str = "api",
    answer_mode: str = "api",
    model: str | None = None,
    fallback_rules: bool = False,
    fallback_template: bool = False,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed_task = task or _parse_task(
        user_message,
        data_dir=data_dir,
        parse_mode=parse_mode,
        model=model,
        fallback_rules=fallback_rules,
        conversation_history=conversation_history,
    )
    _apply_history_exclusions(parsed_task, user_message, conversation_history)
    retrieved_data = retrieve_items_for_task(parsed_task, data_dir=data_dir)
    answer = _answer(
        user_message,
        parsed_task,
        retrieved_data,
        answer_mode=answer_mode,
        model=model,
        fallback_template=fallback_template,
        conversation_history=conversation_history,
    )
    return {
        "answer": answer,
        "task": parsed_task,
        "retrieved_data": retrieved_data,
    }


def _parse_task(
    user_message: str,
    *,
    data_dir: str | None,
    parse_mode: str,
    model: str | None,
    fallback_rules: bool,
    conversation_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if parse_mode == "rules":
        return parse_user_query(user_message, data_dir=data_dir)
    if parse_mode != "api":
        raise ValueError("parse_mode must be 'api' or 'rules'.")

    try:
        return parse_user_query_with_gpt(
            user_message,
            data_dir=data_dir,
            model=model,
            conversation_history=conversation_history,
        )
    except OpenAIParserError:
        if not fallback_rules:
            raise
        task = parse_user_query(user_message, data_dir=data_dir)
        task["parser"] = "offline_rules_fallback"
        return task


def _answer(
    user_message: str,
    task: dict[str, Any],
    retrieved_data: dict[str, Any],
    *,
    answer_mode: str,
    model: str | None,
    fallback_template: bool,
    conversation_history: list[dict[str, Any]] | None,
) -> str:
    if answer_mode == "template":
        return build_template_answer(user_message, task, retrieved_data)
    if answer_mode != "api":
        raise ValueError("answer_mode must be 'api' or 'template'.")

    try:
        return generate_final_answer_with_gpt(
            user_message,
            task,
            retrieved_data,
            model=model,
            conversation_history=conversation_history,
        )
    except FinalAnswerError:
        if not fallback_template:
            raise
        return build_template_answer(user_message, task, retrieved_data)


def _apply_history_exclusions(
    task: dict[str, Any],
    user_message: str,
    conversation_history: list[dict[str, Any]] | None,
) -> None:
    if not conversation_history or not _asks_for_alternative(user_message):
        return

    item_ids: list[str] = []
    for message in reversed(conversation_history):
        if message.get("role") != "assistant":
            continue
        for item_id in message.get("recommendation_item_ids") or []:
            item_id_text = str(item_id).strip()
            if item_id_text and item_id_text not in item_ids:
                item_ids.append(item_id_text)
        if item_ids:
            break

    if not item_ids:
        return

    entities = task.setdefault("entities", {})
    existing = [str(item_id) for item_id in entities.get("exclude_item_ids", [])]
    entities["exclude_item_ids"] = list(dict.fromkeys([*existing, *item_ids]))


def _asks_for_alternative(message: str) -> bool:
    text = _strip_accents(message)
    phrases = [
        "khong ung",
        "khong thich",
        "khong muon",
        "mon khac",
        "quan khac",
        "goi y lai",
        "doi mon",
        "cai khac",
        "lua chon khac",
        "khac di",
    ]
    return any(phrase in text for phrase in phrases)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D").casefold()
