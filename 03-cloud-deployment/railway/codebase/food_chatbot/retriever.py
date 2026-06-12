from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codebase.chatbot_parser.parser import DEFAULT_DATA_DIR


DB_FILENAME = "shopee_food_mock_hcm_q1.sqlite"

FILTER_COLUMN_MAP = {
    "is_available": "v.is_available",
    "shop_status": "v.shop_status",
    "max_effective_price": "v.effective_price",
    "min_effective_price": "v.effective_price",
    "max_estimated_delivery_fee": "v.estimated_delivery_fee",
    "min_spicy_level": "v.spicy_level",
    "max_spicy_level": "v.spicy_level",
    "max_calories_estimate": "v.calories_estimate",
    "max_avg_delivery_time_min": "v.avg_delivery_time_min",
}

RANKING_COLUMN_MAP = {
    "recommendation_score": "v.recommendation_score",
    "item_rating": "v.item_rating",
    "effective_price": "v.effective_price",
    "avg_delivery_time_min": "v.avg_delivery_time_min",
    "item_sold_count": "v.item_sold_count",
    "shop_rating": "v.shop_rating",
    "calories_estimate": "v.calories_estimate",
}

BASE_SELECT = """
SELECT
  v.item_id,
  v.item_name,
  v.base_price,
  v.effective_price,
  v.item_rating,
  v.item_sold_count,
  v.spicy_level,
  v.calories_estimate,
  v.is_available,
  v.is_signature,
  v.category_name,
  v.shop_id,
  v.shop_name,
  v.shop_rating,
  v.shop_status,
  v.avg_delivery_time_min,
  v.min_order_amount,
  v.full_address,
  v.latitude,
  v.longitude,
  v.estimated_delivery_fee,
  v.recommendation_score,
  mi.description,
  mi.portion_size,
  mi.is_combo
FROM v_recommendation_items v
JOIN menu_items mi ON mi.id = v.item_id
"""


def retrieve_items_for_task(
    task: dict[str, Any],
    data_dir: str | Path | None = None,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Query mock_data for food items that match a parsed task JSON."""

    resolved_data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    db_path = resolved_data_dir / DB_FILENAME
    if not db_path.exists():
        raise FileNotFoundError(f"Mock SQLite database not found: {db_path}")

    result_limit = _resolve_limit(task, limit)
    if task.get("intent") == "unknown" or task.get("task_type") == "clarify_food_need":
        return {
            "database_path": str(db_path),
            "items": [],
            "near_misses": [],
            "fallback_items": [],
            "sql": None,
            "params": [],
            "warnings": ["Task needs clarification before querying food data."],
        }

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        sql, params = _build_items_query(task, result_limit)
        rows = con.execute(sql, params).fetchall()
        items = [_row_to_item(con, row, task) for row in rows]

        near_misses: list[dict[str, Any]] = []
        fallback_items: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not items:
            if _entities(task).get("dish_keywords"):
                near_sql, near_params = _build_items_query(
                    task,
                    result_limit,
                    relax={"price", "delivery", "health", "spice", "group"},
                )
                near_rows = con.execute(near_sql, near_params).fetchall()
                near_misses = [_row_to_item(con, row, task) for row in near_rows]
                if near_misses:
                    warnings.append("No strict result; found exact/near item outside some filters.")

            fallback_relax = {"tags"}
            if _entities(task).get("dish_keywords"):
                fallback_relax.add("dish")

            fallback_sql, fallback_params = _build_items_query(
                task,
                result_limit,
                relax=fallback_relax,
            )
            fallback_rows = con.execute(fallback_sql, fallback_params).fetchall()
            fallback_items = [_row_to_item(con, row, task) for row in fallback_rows]

            if not fallback_items and filters_has_price(_filters(task)):
                price_relaxed_sql, price_relaxed_params = _build_items_query(
                    task,
                    result_limit,
                    relax={*fallback_relax, "price"},
                )
                price_relaxed_rows = con.execute(
                    price_relaxed_sql, price_relaxed_params
                ).fetchall()
                fallback_items = [
                    _row_to_item(con, row, task) for row in price_relaxed_rows
                ]

            if fallback_items:
                warnings.append("No strict result; fallback_items relax one or more soft filters.")

    return {
        "database_path": str(db_path),
        "items": items,
        "near_misses": near_misses,
        "fallback_items": fallback_items,
        "sql": _single_line_sql(sql),
        "params": params,
        "warnings": warnings,
    }


def _build_items_query(
    task: dict[str, Any],
    limit: int,
    *,
    relax: set[str] | None = None,
) -> tuple[str, list[Any]]:
    relax = relax or set()
    where: list[str] = ["1 = 1"]
    params: list[Any] = []
    filters = _filters(task)
    entities = _entities(task)

    _add_scalar_filters(where, params, filters, relax)
    _add_discount_filter(where, filters, relax)
    _add_group_filter(where, params, filters, entities, relax)
    _add_include_tags(where, params, entities, relax)
    _add_exclude_tags(where, params, entities)
    _add_exclude_item_ids(where, params, entities)
    _add_cuisines(where, params, entities)
    _add_dish_keywords(where, params, entities, relax)
    _add_allergen_exclusions(where, params, entities)

    order_by = _build_order_by(task)
    params.append(limit)
    sql = f"""
{BASE_SELECT}
WHERE {' AND '.join(where)}
{order_by}
LIMIT ?
"""
    return sql, params


def _add_scalar_filters(
    where: list[str],
    params: list[Any],
    filters: dict[str, Any],
    relax: set[str],
) -> None:
    direct_equals = ["is_available", "shop_status"]
    for key in direct_equals:
        value = filters.get(key)
        if value is not None:
            where.append(f"{FILTER_COLUMN_MAP[key]} = ?")
            params.append(value)

    if "price" not in relax:
        _add_max(where, params, filters, "max_effective_price")
        _add_min(where, params, filters, "min_effective_price")

    if "delivery" not in relax:
        _add_max(where, params, filters, "max_estimated_delivery_fee")
        _add_max(where, params, filters, "max_avg_delivery_time_min")

    if "spice" not in relax:
        _add_min(where, params, filters, "min_spicy_level")
        _add_max(where, params, filters, "max_spicy_level")

    if "health" not in relax:
        _add_max(where, params, filters, "max_calories_estimate")


def _add_max(where: list[str], params: list[Any], filters: dict[str, Any], key: str) -> None:
    value = filters.get(key)
    if value is not None:
        where.append(f"{FILTER_COLUMN_MAP[key]} <= ?")
        params.append(value)


def _add_min(where: list[str], params: list[Any], filters: dict[str, Any], key: str) -> None:
    value = filters.get(key)
    if value is not None:
        where.append(f"{FILTER_COLUMN_MAP[key]} >= ?")
        params.append(value)


def _add_discount_filter(
    where: list[str],
    filters: dict[str, Any],
    relax: set[str],
) -> None:
    if filters.get("requires_discount") is True and "price" not in relax:
        where.append(
            """(
              v.effective_price < v.base_price OR EXISTS (
                SELECT 1
                FROM item_promotions ip
                JOIN promotions p ON p.id = ip.promotion_id
                WHERE ip.item_id = v.item_id AND p.is_active = 1
              )
            )"""
        )


def _add_group_filter(
    where: list[str],
    params: list[Any],
    filters: dict[str, Any],
    entities: dict[str, Any],
    relax: set[str],
) -> None:
    if filters.get("min_portion_people") is None or "group" in relax:
        return

    where.append(
        """(
          mi.is_combo = 1
          OR mi.portion_size LIKE ?
          OR mi.portion_size LIKE ?
          OR EXISTS (
            SELECT 1
            FROM item_tags it
            JOIN tags t ON t.id = it.tag_id
            WHERE it.item_id = v.item_id AND t.name IN ('combo', 'ăn nhóm')
          )
        )"""
    )
    people = int(filters["min_portion_people"])
    params.extend([f"%{people}%", "%2 người%"])
    entities.setdefault("party_size", people)


def _add_include_tags(
    where: list[str],
    params: list[Any],
    entities: dict[str, Any],
    relax: set[str],
) -> None:
    if "tags" in relax:
        return

    for tag in _as_list(entities.get("include_tags")):
        where.append(
            """(
              EXISTS (
                SELECT 1
                FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE it.item_id = v.item_id AND t.name = ? COLLATE NOCASE
              )
              OR v.category_name LIKE ?
              OR v.item_name LIKE ?
              OR mi.description LIKE ?
            )"""
        )
        like_value = f"%{tag}%"
        params.extend([tag, like_value, like_value, like_value])


def _add_exclude_tags(
    where: list[str],
    params: list[Any],
    entities: dict[str, Any],
) -> None:
    for tag in _as_list(entities.get("exclude_tags")):
        where.append(
            """NOT (
              EXISTS (
                SELECT 1
                FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE it.item_id = v.item_id AND t.name = ? COLLATE NOCASE
              )
              OR v.category_name LIKE ?
              OR v.item_name LIKE ?
              OR mi.description LIKE ?
            )"""
        )
        like_value = f"%{tag}%"
        params.extend([tag, like_value, like_value, like_value])


def _add_exclude_item_ids(
    where: list[str],
    params: list[Any],
    entities: dict[str, Any],
) -> None:
    item_ids = _as_list(entities.get("exclude_item_ids"))
    if not item_ids:
        return

    placeholders = ",".join("?" for _ in item_ids)
    where.append(f"v.item_id NOT IN ({placeholders})")
    params.extend(item_ids)


def _add_cuisines(
    where: list[str],
    params: list[Any],
    entities: dict[str, Any],
) -> None:
    cuisines = _as_list(entities.get("include_cuisines"))
    if not cuisines:
        return

    placeholders = ",".join("?" for _ in cuisines)
    where.append(
        f"""EXISTS (
          SELECT 1
          FROM shop_cuisines sc
          JOIN cuisines c ON c.id = sc.cuisine_id
          WHERE sc.shop_id = v.shop_id AND c.name IN ({placeholders})
        )"""
    )
    params.extend(cuisines)


def _add_dish_keywords(
    where: list[str],
    params: list[Any],
    entities: dict[str, Any],
    relax: set[str],
) -> None:
    if "dish" in relax:
        return

    for keyword in _as_list(entities.get("dish_keywords")):
        where.append("(v.item_name LIKE ? OR mi.description LIKE ?)")
        like_value = f"%{keyword}%"
        params.extend([like_value, like_value])


def _add_allergen_exclusions(
    where: list[str],
    params: list[Any],
    entities: dict[str, Any],
) -> None:
    for allergen in _as_list(entities.get("exclude_allergens")):
        where.append(
            """NOT (
              EXISTS (
                SELECT 1
                FROM item_allergens ia
                JOIN allergens a ON a.id = ia.allergen_id
                WHERE ia.item_id = v.item_id AND a.name = ? COLLATE NOCASE
              )
              OR EXISTS (
                SELECT 1
                FROM item_tags it
                JOIN tags t ON t.id = it.tag_id
                WHERE it.item_id = v.item_id AND t.name = ? COLLATE NOCASE
              )
              OR v.item_name LIKE ?
              OR mi.description LIKE ?
            )"""
        )
        like_value = f"%{allergen}%"
        params.extend([allergen, allergen, like_value, like_value])


def _build_order_by(task: dict[str, Any]) -> str:
    order_parts: list[str] = []
    for field, direction in (task.get("ranking") or {}).items():
        column = RANKING_COLUMN_MAP.get(field)
        if not column:
            continue
        normalized_direction = str(direction).lower()
        if normalized_direction not in {"asc", "desc"}:
            continue
        order_parts.append(f"{column} {normalized_direction.upper()}")

    if "v.recommendation_score DESC" not in order_parts:
        order_parts.append("v.recommendation_score DESC")
    return "ORDER BY " + ", ".join(order_parts)


def _row_to_item(
    con: sqlite3.Connection,
    row: sqlite3.Row,
    task: dict[str, Any],
) -> dict[str, Any]:
    item = {key: row[key] for key in row.keys()}
    item["tags"] = _list_query(
        con,
        """
        SELECT t.name
        FROM item_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.item_id = ?
        ORDER BY t.name
        """,
        row["item_id"],
    )
    item["allergens"] = _list_query(
        con,
        """
        SELECT a.name
        FROM item_allergens ia
        JOIN allergens a ON a.id = ia.allergen_id
        WHERE ia.item_id = ?
        ORDER BY a.name
        """,
        row["item_id"],
    )
    item["promotions"] = _list_query(
        con,
        """
        SELECT p.name
        FROM item_promotions ip
        JOIN promotions p ON p.id = ip.promotion_id
        WHERE ip.item_id = ? AND p.is_active = 1
        ORDER BY p.name
        """,
        row["item_id"],
    )
    item["match_reasons"] = _match_reasons(item, task)
    return item


def _list_query(con: sqlite3.Connection, sql: str, item_id: str) -> list[str]:
    return [row[0] for row in con.execute(sql, [item_id]).fetchall()]


def _match_reasons(item: dict[str, Any], task: dict[str, Any]) -> list[str]:
    filters = _filters(task)
    entities = _entities(task)
    reasons: list[str] = []

    if filters.get("max_effective_price") is not None:
        if item["effective_price"] <= filters["max_effective_price"]:
            reasons.append(
                f"giá {item['effective_price']:,}đ <= {filters['max_effective_price']:,}đ"
            )
        else:
            reasons.append(
                f"giá {item['effective_price']:,}đ vượt ngân sách {filters['max_effective_price']:,}đ"
            )
    if filters.get("max_avg_delivery_time_min") is not None:
        if item["avg_delivery_time_min"] <= filters["max_avg_delivery_time_min"]:
            reasons.append(f"giao khoảng {item['avg_delivery_time_min']} phút")
        else:
            reasons.append(
                f"giao khoảng {item['avg_delivery_time_min']} phút, lâu hơn mức {filters['max_avg_delivery_time_min']} phút"
            )
    if filters.get("min_spicy_level") is not None:
        reasons.append(f"độ cay {item['spicy_level']}/5")
    if filters.get("max_calories_estimate") is not None:
        reasons.append(f"khoảng {item['calories_estimate']} kcal")
    if entities.get("include_tags"):
        matched_tags = sorted(set(item.get("tags", [])) & set(entities["include_tags"]))
        if matched_tags:
            reasons.append("khớp tag " + ", ".join(matched_tags))
    if item.get("promotions"):
        reasons.append("có khuyến mãi")
    if item.get("is_signature"):
        reasons.append("món signature")
    return reasons


def _resolve_limit(task: dict[str, Any], limit: int | None) -> int:
    raw_limit = limit if limit is not None else task.get("limit", 10)
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        value = 10
    return max(1, min(20, value))


def _filters(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("filters") or {}


def filters_has_price(filters: dict[str, Any]) -> bool:
    return filters.get("max_effective_price") is not None or filters.get(
        "min_effective_price"
    ) is not None


def _entities(task: dict[str, Any]) -> dict[str, Any]:
    entities = task.get("entities") or {}
    if not isinstance(entities, dict):
        return {}
    return entities


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _single_line_sql(sql: str) -> str:
    return " ".join(sql.split())
