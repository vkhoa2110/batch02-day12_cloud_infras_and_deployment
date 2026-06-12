from __future__ import annotations

import csv
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = (
    Path(__file__).resolve().parents[1] / "mock_data" / "shopee_food_db_hcm_q1"
)


INTENT_KEYWORDS = {
    "recommendation": [
        "goi y",
        "de xuat",
        "an gi",
        "mon nao",
        "nen an",
        "muon an",
        "tim mon",
        "chon mon",
    ],
    "budget_meal": [
        "duoi",
        "khong qua",
        "ko qua",
        "toi da",
        "tam gia",
        "gia re",
        "re",
        "budget",
        "ngan sach",
        "sinh vien",
    ],
    "healthy_food": [
        "healthy",
        "eat clean",
        "it dau mo",
        "it beo",
        "it calo",
        "low calo",
        "an kieng",
        "detox",
        "protein cao",
    ],
    "spicy_food": [
        "cay",
        "cay cay",
        "rat cay",
        "sieu cay",
        "mi cay",
        "chua cay",
    ],
    "fast_delivery": [
        "giao nhanh",
        "nhanh nhat",
        "nhanh gon",
        "co lien",
        "doi qua",
        "dang doi",
    ],
    "vegetarian": [
        "an chay",
        "mon chay",
        "do chay",
        "chay",
        "vegetarian",
        "vegan",
    ],
    "avoid_allergen": [
        "di ung",
        "khong an duoc",
        "tranh",
        "dung co",
        "khong lay",
        "khong hai san",
    ],
    "group_order": [
        "an nhom",
        "cho nhom",
        "nhom",
        "combo",
        "gia dinh",
        "nhieu nguoi",
    ],
    "breakfast": ["an sang", "bua sang", "sang nay", "buoi sang"],
    "lunch": ["an trua", "bua trua", "trua nay", "buoi trua"],
    "dinner": ["an toi", "bua toi", "toi nay", "buoi toi"],
    "late_night": ["an khuya", "dem", "khuya"],
    "snack": ["an vat", "an nhe", "trang mieng"],
}


TAG_SYNONYMS = {
    "healthy": ["healthy", "eat clean", "lanh manh"],
    "ít dầu mỡ": ["it dau mo", "it dau", "it beo"],
    "ăn kiêng": ["an kieng", "diet"],
    "protein cao": ["protein cao", "nhieu protein"],
    "detox": ["detox"],
    "cay": ["cay", "cay cay"],
    "món cay": ["mon cay"],
    "không cay": ["khong cay"],
    "ít cay": ["it cay"],
    "rất cay": ["rat cay", "sieu cay"],
    "ăn sáng": ["an sang", "bua sang", "sang nay"],
    "ăn trưa": ["an trua", "bua trua", "trua nay"],
    "ăn tối": ["an toi", "bua toi", "toi nay"],
    "ăn khuya": ["an khuya", "khuya"],
    "ăn vặt": ["an vat"],
    "ăn nhẹ": ["an nhe"],
    "ăn nhóm": ["an nhom", "cho nhom", "gia dinh", "nhieu nguoi"],
    "combo": ["combo", "set"],
    "giao nhanh": ["giao nhanh", "nhanh gon", "co lien"],
    "rẻ": ["gia re", "re", "sinh vien"],
    "bán chạy": ["ban chay", "popular", "nhieu nguoi mua"],
    "đang giảm giá": ["giam gia", "khuyen mai", "sale", "deal", "uu dai"],
    "signature": ["signature", "dac trung", "best seller", "dac biet"],
}


DEFAULT_RANKING = OrderedDict(
    [
        ("recommendation_score", "desc"),
        ("item_rating", "desc"),
        ("effective_price", "asc"),
    ]
)


NEGATION_WORDS = {
    "khong",
    "ko",
    "tranh",
    "dung",
    "dung co",
    "khong lay",
    "khong an",
}


def parse_user_query(message: str, data_dir: str | Path | None = None) -> dict[str, Any]:
    """Convert a Vietnamese food-recommendation message into task JSON.

    The output is intentionally deterministic and database-shaped. It does not call
    an LLM, so it is suitable as a first NLU step before SQL search or AI reranking.
    """

    vocab = _load_vocab(Path(data_dir) if data_dir else DEFAULT_DATA_DIR)
    normalized = _normalize(message)
    filters: dict[str, Any] = {
        "is_available": 1,
        "shop_status": "open",
    }
    entities: dict[str, Any] = {
        "include_tags": [],
        "exclude_tags": [],
        "include_cuisines": [],
        "dish_keywords": [],
        "exclude_allergens": [],
    }
    ranking: OrderedDict[str, str] = OrderedDict(DEFAULT_RANKING)
    signals: list[str] = []
    intent_scores: dict[str, int] = {}

    _score_intents(normalized, intent_scores, signals)
    _extract_prices(normalized, filters, intent_scores, signals)
    _extract_delivery_fee(normalized, filters, signals)
    _extract_people(normalized, filters, entities, intent_scores, signals)
    _extract_vegetarian(normalized, entities, intent_scores, signals)
    _extract_spice(normalized, filters, entities, intent_scores, signals)
    _extract_health(normalized, filters, entities, intent_scores, signals)
    _extract_speed(normalized, filters, ranking, intent_scores, signals)
    _extract_discount(normalized, filters, entities, ranking, intent_scores, signals)
    _extract_quality_ranking(normalized, ranking, entities, signals)
    _extract_vocab_matches(normalized, vocab, entities, intent_scores, signals)
    _extract_negative_preferences(normalized, vocab, entities, signals)

    _dedupe_entity_lists(entities)
    _clean_empty_entities(entities)

    primary_intent, sub_intents = _choose_intents(intent_scores, entities, filters)
    confidence = _estimate_confidence(primary_intent, signals, entities, filters)
    needs_clarification, questions = _clarification_state(
        normalized, primary_intent, confidence, entities
    )

    task_type = "recommend_items"
    if primary_intent == "unknown":
        task_type = "clarify_food_need"
    elif entities.get("dish_keywords"):
        task_type = "search_or_recommend_items"

    return {
        "version": "food_task.v1",
        "source_text": message,
        "task_type": task_type,
        "intent": "recommend_items" if primary_intent != "unknown" else "unknown",
        "primary_intent": primary_intent,
        "sub_intents": sub_intents,
        "entities": entities,
        "filters": filters,
        "ranking": dict(ranking),
        "limit": 10,
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarifying_questions": questions,
        "debug_signals": signals,
    }


def _normalize(text: str) -> str:
    text = text.casefold().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", text)
    text = re.sub(r"[^a-z0-9.,+\-<=/>=% ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return f" {text.strip()} "


def _load_vocab(data_dir: Path) -> dict[str, list[dict[str, str]]]:
    return {
        "tags": _read_name_rows(data_dir / "tags.csv", "name", "tag_type"),
        "cuisines": _read_name_rows(data_dir / "cuisines.csv", "name", "parent_name"),
        "allergens": _read_name_rows(data_dir / "allergens.csv", "name"),
        "menu_items": _read_name_rows(data_dir / "menu_items.csv", "name"),
        "categories": _read_name_rows(data_dir / "menu_categories.csv", "name"),
    }


def _read_name_rows(path: Path, name_col: str, extra_col: str | None = None) -> list[dict[str, str]]:
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            value = {"name": name, "normalized": _normalize(name).strip()}
            if extra_col:
                value[extra_col] = (row.get(extra_col) or "").strip()
            rows.append(value)
    return rows


def _contains(text: str, phrase: str) -> bool:
    return _find_phrase_span(text, phrase) is not None


def _find_phrase_span(text: str, phrase: str) -> tuple[int, int] | None:
    phrase = _normalize(phrase).strip()
    if not phrase:
        return None
    pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
    match = re.search(pattern, text)
    if not match:
        return None
    return match.start(), match.end()


def _score_intents(text: str, intent_scores: dict[str, int], signals: list[str]) -> None:
    for intent, keywords in INTENT_KEYWORDS.items():
        matched = [keyword for keyword in keywords if _contains(text, keyword)]
        if matched:
            score = 1 if intent == "recommendation" else 3
            intent_scores[intent] = intent_scores.get(intent, 0) + score + len(matched) - 1
            signals.append(f"intent:{intent}:{','.join(matched[:3])}")


def _extract_prices(
    text: str,
    filters: dict[str, Any],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    price_spans = list(_iter_price_mentions(text))
    if not price_spans:
        if any(_contains(text, word) for word in ["gia re", "re", "sinh vien"]):
            filters.setdefault("max_effective_price", 50000)
            intent_scores["budget_meal"] = intent_scores.get("budget_meal", 0) + 2
            signals.append("price:implicit_cheap:50000")
        return

    range_match = re.search(
        rf"(?:tu|khoang)?\s*{_PRICE_PATTERN}\s*(?:den|toi|-|/)\s*{_PRICE_PATTERN}",
        text,
    )
    if range_match:
        lower = _parse_amount(range_match.group(1), range_match.group(2), has_price_context=True)
        upper = _parse_amount(range_match.group(3), range_match.group(4), has_price_context=True)
        if lower and upper:
            filters["min_effective_price"] = min(lower, upper)
            filters["max_effective_price"] = max(lower, upper)
            intent_scores["budget_meal"] = intent_scores.get("budget_meal", 0) + 3
            signals.append(f"price:range:{filters['min_effective_price']}-{filters['max_effective_price']}")
            return

    for amount, start, end in price_spans:
        before = text[max(0, start - 28) : start]
        after = text[end : min(len(text), end + 24)]
        nearby = f"{before} {after}"
        if _looks_like_delivery_fee_context(nearby):
            continue
        if re.search(r"(tren|hon|tu|toi thieu|min|>=|lon hon)\s*$", before):
            filters["min_effective_price"] = amount
            signals.append(f"price:min:{amount}")
        else:
            filters["max_effective_price"] = amount
            signals.append(f"price:max:{amount}")
        intent_scores["budget_meal"] = intent_scores.get("budget_meal", 0) + 3
        break


_PRICE_PATTERN = r"(\d+(?:[.,]\d+)*)\s*(k|nghin|ngan|000|d|dong|vnd)?"


def _iter_price_mentions(text: str) -> list[tuple[int, int, int]]:
    mentions: list[tuple[int, int, int]] = []
    for match in re.finditer(_PRICE_PATTERN, text):
        number, unit = match.group(1), match.group(2)
        before = text[max(0, match.start() - 18) : match.start()]
        after = text[match.end() : min(len(text), match.end() + 18)]
        context = f"{before} {after}"
        has_price_context = bool(
            unit
            or re.search(
                r"(gia|duoi|tren|hon|tam|khoang|ngan sach|budget|vnd|dong|re|ship|phi)",
                context,
            )
        )
        if not has_price_context:
            continue
        amount = _parse_amount(number, unit, has_price_context)
        if amount is None:
            continue
        mentions.append((amount, match.start(), match.end()))
    return mentions


def _parse_amount(number_text: str, unit: str | None, has_price_context: bool) -> int | None:
    cleaned = number_text.strip()
    if not cleaned:
        return None

    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", cleaned):
        value = float(re.sub(r"[.,]", "", cleaned))
    elif "," in cleaned or "." in cleaned:
        value = float(cleaned.replace(",", "."))
    else:
        value = float(cleaned)

    unit = unit or ""
    if unit in {"k", "nghin", "ngan"}:
        value *= 1000
    elif unit == "000":
        value *= 1000
    elif not unit and has_price_context and value <= 300:
        value *= 1000

    return int(round(value))


def _extract_delivery_fee(text: str, filters: dict[str, Any], signals: list[str]) -> None:
    for amount, start, end in _iter_price_mentions(text):
        nearby = text[max(0, start - 24) : min(len(text), end + 24)]
        if _looks_like_delivery_fee_context(nearby):
            filters["max_estimated_delivery_fee"] = amount
            signals.append(f"delivery_fee:max:{amount}")
            return


def _looks_like_delivery_fee_context(text: str) -> bool:
    return bool(re.search(r"(ship|phi giao|giao hang|delivery fee)", text))


def _extract_people(
    text: str,
    filters: dict[str, Any],
    entities: dict[str, Any],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    match = re.search(r"(\d+)\s*(?:nguoi|ban|phan|suat)", text)
    if match:
        people = int(match.group(1))
        if people > 1:
            entities["party_size"] = people
            filters["min_portion_people"] = min(people, 4)
            entities["include_tags"].extend(["ăn nhóm", "combo"])
            intent_scores["group_order"] = intent_scores.get("group_order", 0) + 3
            signals.append(f"party_size:{people}")
    elif any(_contains(text, word) for word in ["nhom", "gia dinh", "nhieu nguoi"]):
        filters["min_portion_people"] = 2
        entities["include_tags"].extend(["ăn nhóm", "combo"])
        intent_scores["group_order"] = intent_scores.get("group_order", 0) + 3
        signals.append("party_size:implicit_group")


def _extract_vegetarian(
    text: str,
    entities: dict[str, Any],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    if any(_contains(text, word) for word in INTENT_KEYWORDS["vegetarian"]):
        entities["include_tags"].append("chay")
        entities["include_cuisines"].append("Chay")
        intent_scores["vegetarian"] = intent_scores.get("vegetarian", 0) + 3
        signals.append("diet:vegetarian")


def _extract_spice(
    text: str,
    filters: dict[str, Any],
    entities: dict[str, Any],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    if _contains(text, "khong cay"):
        filters["max_spicy_level"] = 0
        entities["include_tags"].append("không cay")
        signals.append("spice:max:0")
    elif any(_contains(text, word) for word in ["it cay", "nhe cay"]):
        filters["max_spicy_level"] = 1
        entities["include_tags"].append("ít cay")
        signals.append("spice:max:1")
    elif any(_contains(text, word) for word in ["rat cay", "sieu cay", "cay nhieu"]):
        filters["min_spicy_level"] = 4
        entities["include_tags"].extend(["cay", "rất cay"])
        intent_scores["spicy_food"] = intent_scores.get("spicy_food", 0) + 3
        signals.append("spice:min:4")
    elif _contains(text, "cay"):
        filters["min_spicy_level"] = 3
        entities["include_tags"].append("cay")
        intent_scores["spicy_food"] = intent_scores.get("spicy_food", 0) + 3
        signals.append("spice:min:3")


def _extract_health(
    text: str,
    filters: dict[str, Any],
    entities: dict[str, Any],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    health_tags = []
    for tag in ["healthy", "ít dầu mỡ", "ăn kiêng", "protein cao", "detox"]:
        if any(_contains(text, phrase) for phrase in TAG_SYNONYMS[tag]):
            health_tags.append(tag)

    if health_tags:
        entities["include_tags"].extend(health_tags)
        filters.setdefault("max_calories_estimate", 650)
        intent_scores["healthy_food"] = intent_scores.get("healthy_food", 0) + 3
        signals.append(f"health:{','.join(health_tags)}")

    calorie_match = re.search(r"(?:duoi|khong qua|toi da|<)\s*(\d{2,4})\s*(?:calo|cal|kcal)", text)
    if calorie_match:
        filters["max_calories_estimate"] = int(calorie_match.group(1))
        signals.append(f"calories:max:{filters['max_calories_estimate']}")


def _extract_speed(
    text: str,
    filters: dict[str, Any],
    ranking: OrderedDict[str, str],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    if any(_contains(text, word) for word in INTENT_KEYWORDS["fast_delivery"]):
        filters.setdefault("max_avg_delivery_time_min", 20)
        _promote_ranking(ranking, "avg_delivery_time_min", "asc")
        intent_scores["fast_delivery"] = intent_scores.get("fast_delivery", 0) + 3
        signals.append("delivery:fast")

    minute_match = re.search(r"(?:duoi|trong|khong qua|toi da)\s*(\d{1,2})\s*(?:phut|min)", text)
    if minute_match:
        filters["max_avg_delivery_time_min"] = int(minute_match.group(1))
        _promote_ranking(ranking, "avg_delivery_time_min", "asc")
        signals.append(f"delivery:max_min:{filters['max_avg_delivery_time_min']}")


def _extract_discount(
    text: str,
    filters: dict[str, Any],
    entities: dict[str, Any],
    ranking: OrderedDict[str, str],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    if any(_contains(text, word) for word in TAG_SYNONYMS["đang giảm giá"]):
        filters["requires_discount"] = True
        entities["include_tags"].append("đang giảm giá")
        _promote_ranking(ranking, "effective_price", "asc")
        intent_scores["budget_meal"] = intent_scores.get("budget_meal", 0) + 1
        signals.append("discount:true")


def _extract_quality_ranking(
    text: str,
    ranking: OrderedDict[str, str],
    entities: dict[str, Any],
    signals: list[str],
) -> None:
    if any(_contains(text, word) for word in ["ngon", "rating cao", "danh gia cao", "tot nhat"]):
        _promote_ranking(ranking, "item_rating", "desc")
        _promote_ranking(ranking, "shop_rating", "desc")
        signals.append("ranking:rating")
    if any(_contains(text, word) for word in TAG_SYNONYMS["bán chạy"]):
        entities["include_tags"].append("bán chạy")
        _promote_ranking(ranking, "item_sold_count", "desc")
        signals.append("ranking:sold")
    if any(_contains(text, word) for word in TAG_SYNONYMS["signature"]):
        filters_value = True
        entities["include_tags"].append("signature")
        signals.append(f"signature:{filters_value}")


def _extract_vocab_matches(
    text: str,
    vocab: dict[str, list[dict[str, str]]],
    entities: dict[str, Any],
    intent_scores: dict[str, int],
    signals: list[str],
) -> None:
    for tag, phrases in TAG_SYNONYMS.items():
        if any(_contains(text, phrase) for phrase in phrases):
            entities["include_tags"].append(tag)

    for allergen in _matching_vocab_entries(text, vocab["allergens"]):
        if _has_negation_near(text, allergen["normalized"]):
            entities["exclude_allergens"].append(allergen["name"])
            intent_scores["avoid_allergen"] = intent_scores.get("avoid_allergen", 0) + 3
            signals.append(f"allergen:exclude:{allergen['name']}")

    for cuisine in _matching_vocab_entries(text, vocab["cuisines"]):
        if not _has_negation_near(text, cuisine["normalized"]):
            entities["include_cuisines"].append(cuisine["name"])
            signals.append(f"cuisine:{cuisine['name']}")

    for category in _matching_vocab_entries(text, vocab["categories"]):
        if not _has_negation_near(text, category["normalized"]):
            entities["include_tags"].append(category["name"].casefold())
            signals.append(f"category:{category['name']}")

    for item in _matching_vocab_entries(text, vocab["menu_items"], min_chars=5):
        if not _has_negation_near(text, item["normalized"]):
            entities["dish_keywords"].append(item["name"])
            signals.append(f"dish:{item['name']}")

    if entities["dish_keywords"]:
        intent_scores["specific_item_search"] = intent_scores.get("specific_item_search", 0) + 2


def _matching_vocab_entries(
    text: str,
    rows: list[dict[str, str]],
    min_chars: int = 2,
) -> list[dict[str, str]]:
    matches = []
    for row in rows:
        normalized = row["normalized"]
        if len(normalized) < min_chars:
            continue
        if normalized == "goi" and _contains(text, "goi y"):
            continue
        if _find_phrase_span(text, normalized):
            matches.append(row)
    matches.sort(key=lambda row: len(row["normalized"]), reverse=True)
    return matches


def _has_negation_near(text: str, normalized_phrase: str) -> bool:
    span = _find_phrase_span(text, normalized_phrase)
    if not span:
        return False
    index = span[0]
    before = text[max(0, index - 24) : index].strip()
    return any(before.endswith(word) or f" {word} " in f" {before} " for word in NEGATION_WORDS)


def _extract_negative_preferences(
    text: str,
    vocab: dict[str, list[dict[str, str]]],
    entities: dict[str, Any],
    signals: list[str],
) -> None:
    for tag in vocab["tags"]:
        normalized = tag["normalized"]
        if normalized and _has_negation_near(text, normalized):
            if tag["name"] not in entities["exclude_tags"]:
                entities["exclude_tags"].append(tag["name"])
                signals.append(f"tag:exclude:{tag['name']}")


def _promote_ranking(ranking: OrderedDict[str, str], field: str, direction: str) -> None:
    current = list(ranking.items())
    ranking.clear()
    ranking[field] = direction
    for key, value in current:
        if key != field:
            ranking[key] = value


def _dedupe_entity_lists(entities: dict[str, Any]) -> None:
    for key, value in list(entities.items()):
        if not isinstance(value, list):
            continue
        deduped = []
        seen = set()
        for item in value:
            marker = _normalize(str(item)).strip()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        entities[key] = deduped


def _clean_empty_entities(entities: dict[str, Any]) -> None:
    for key in list(entities.keys()):
        value = entities[key]
        if value == [] or value == {} or value is None:
            del entities[key]


def _choose_intents(
    intent_scores: dict[str, int],
    entities: dict[str, Any],
    filters: dict[str, Any],
) -> tuple[str, list[str]]:
    if not intent_scores and (entities or len(filters) > 2):
        intent_scores["recommendation"] = 1

    if not intent_scores:
        return "unknown", []

    if "recommendation" not in intent_scores:
        intent_scores["recommendation"] = 1

    ranked = sorted(intent_scores.items(), key=lambda item: (-item[1], item[0]))
    primary = next((intent for intent, _score in ranked if intent != "recommendation"), ranked[0][0])
    if primary == "specific_item_search":
        primary = "recommendation"

    sub_intents = [intent for intent, score in ranked if score > 0 and intent != "recommendation"]
    return primary, sub_intents


def _estimate_confidence(
    primary_intent: str,
    signals: list[str],
    entities: dict[str, Any],
    filters: dict[str, Any],
) -> float:
    if primary_intent == "unknown":
        return 0.2
    score = 0.45 + min(len(signals), 6) * 0.06
    if entities.get("dish_keywords") or entities.get("include_tags") or entities.get("include_cuisines"):
        score += 0.08
    if any(key.startswith(("max_", "min_")) for key in filters):
        score += 0.07
    return round(min(score, 0.92), 2)


def _clarification_state(
    text: str,
    primary_intent: str,
    confidence: float,
    entities: dict[str, Any],
) -> tuple[bool, list[str]]:
    if primary_intent == "unknown" or confidence < 0.45:
        return True, ["Bạn muốn mình gợi ý món theo tiêu chí nào: giá, món, độ cay, healthy hay giao nhanh?"]

    if not any(
        [
            entities.get("dish_keywords"),
            entities.get("include_tags"),
            entities.get("include_cuisines"),
        ]
    ) and not any(_contains(text, word) for word in INTENT_KEYWORDS["recommendation"]):
        return True, ["Bạn muốn tìm món cụ thể hay muốn mình gợi ý vài món phù hợp?"]

    return False, []
