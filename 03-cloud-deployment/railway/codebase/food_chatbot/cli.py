from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codebase.chatbot_parser.openai_parser import DEFAULT_OPENAI_MODEL, OpenAIParserError

from .answerer import FinalAnswerError
from .pipeline import run_food_chatbot


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Run the full ShopeeFood chatbot flow: parse -> retrieve -> final LLM answer."
    )
    parser.add_argument("message", nargs="?", help="User message.")
    parser.add_argument(
        "--task-json",
        type=str,
        default=None,
        help="Path to a parsed task JSON file, or '-' to read JSON from stdin.",
    )
    parser.add_argument(
        "--parse-mode",
        choices=["api", "rules"],
        default="api",
        help="How to parse the message when --task-json is not provided.",
    )
    parser.add_argument(
        "--answer-mode",
        choices=["api", "template"],
        default="api",
        help="api calls GPT-4o mini for final text; template is offline fallback.",
    )
    parser.add_argument(
        "--fallback-rules",
        action="store_true",
        help="If API parsing fails, fall back to the offline parser.",
    )
    parser.add_argument(
        "--fallback-template",
        action="store_true",
        help="If final LLM answering fails, fall back to template text.",
    )
    parser.add_argument(
        "--show-json",
        action="store_true",
        help="Print parsed task and retrieved rows after the final answer.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model for parser and final answer API calls.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Path to shopee_food_db_hcm_q1 mock data folder.",
    )
    args = parser.parse_args()

    task = _load_task(args.task_json) if args.task_json else None
    message = args.message or (task or {}).get("source_text")
    if not message:
        print("Provide a message or --task-json containing source_text.", file=sys.stderr)
        return 2

    try:
        result = run_food_chatbot(
            message,
            task=task,
            data_dir=str(args.data_dir) if args.data_dir else None,
            parse_mode=args.parse_mode,
            answer_mode=args.answer_mode,
            model=args.model,
            fallback_rules=args.fallback_rules,
            fallback_template=args.fallback_template,
        )
    except (OpenAIParserError, FinalAnswerError) as exc:
        print(f"OpenAI call failed: {exc}", file=sys.stderr)
        print(
            "Set a valid OPENAI_API_KEY, or run with --parse-mode rules --answer-mode template.",
            file=sys.stderr,
        )
        return 1

    print(result["answer"])
    if args.show_json:
        print("\n--- task_and_retrieval_json ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _load_task(path_value: str) -> dict:
    if path_value == "-":
        return json.loads(sys.stdin.read())

    path = Path(path_value)
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)
