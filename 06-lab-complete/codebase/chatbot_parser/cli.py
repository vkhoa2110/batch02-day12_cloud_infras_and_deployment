import argparse
import json
import sys
from pathlib import Path

from .openai_parser import DEFAULT_OPENAI_MODEL, OpenAIParserError, parse_user_query_with_gpt
from .parser import parse_user_query


EXAMPLE_MESSAGES = [
    "Gợi ý món dưới 50k gần tôi",
    "Tôi muốn ăn bánh khọt Vũng Tàu, không hải sản, tầm 60k",
    "Có món nào cay cay ăn tối giao nhanh không?",
    "Tôi ăn chay, đặt cho nhóm 3 người",
    "Món healthy ít dầu mỡ dưới 70 nghìn",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Parse Vietnamese ShopeeFood chatbot input into task JSON."
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="User message. If omitted, runs built-in demo examples.",
    )
    parser.add_argument(
        "--mode",
        choices=["api", "rules"],
        default="api",
        help="api calls GPT-4o mini; rules runs the offline fallback parser.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model for --mode api.",
    )
    parser.add_argument(
        "--fallback-rules",
        action="store_true",
        help="If API parsing fails, fall back to the offline parser.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Path to shopee_food_db_hcm_q1 CSV folder.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact one-line JSON.",
    )
    args = parser.parse_args()

    messages = [args.message] if args.message else EXAMPLE_MESSAGES
    indent = None if args.compact else 2

    for index, message in enumerate(messages):
        try:
            if args.mode == "api":
                task = parse_user_query_with_gpt(
                    message,
                    data_dir=args.data_dir,
                    model=args.model,
                )
            else:
                task = parse_user_query(message, data_dir=args.data_dir)
        except OpenAIParserError as exc:
            if not args.fallback_rules:
                print(f"OpenAI parser failed: {exc}", file=sys.stderr)
                print(
                    "Set OPENAI_API_KEY, or use --mode rules for offline parsing.",
                    file=sys.stderr,
                )
                return 1
            task = parse_user_query(message, data_dir=args.data_dir)
            task["parser"] = "offline_rules_fallback"
            task["api_error"] = str(exc)

        if len(messages) > 1:
            print(f"\n# {message}")
        print(json.dumps(task, ensure_ascii=False, indent=indent))
        if args.compact:
            print()

    return 0
