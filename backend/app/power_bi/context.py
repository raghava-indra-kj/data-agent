from __future__ import annotations

import json
import math
import re

from app.core.errors import AppError
from app.power_bi.schemas import ReportContext


def _invalid() -> AppError:
    return AppError(
        "POWER_BI_CONTEXT_UNSUPPORTED",
        "This report view contains filters we cannot reproduce. "
        "Choose Entire model or simplify the filters.",
        422,
    )


def literal(value: object) -> str:
    if value is None:
        return "BLANK()"
    if isinstance(value, bool):
        return "TRUE()" if value else "FALSE()"
    if isinstance(value, (int, float)) and math.isfinite(value):
        return str(value)
    if isinstance(value, str) and len(value) <= 4000:
        return '"' + value.replace('"', '""') + '"'
    raise _invalid()


def filter_expression(item: dict[str, object]) -> str | None:
    target = item.get("target")
    if not isinstance(target, dict) or set(target) != {"table", "column"}:
        raise _invalid()
    table, column = target.get("table"), target.get("column")
    if not isinstance(table, str) or not isinstance(column, str) or not table or not column:
        raise _invalid()
    field = "'" + table.replace("'", "''") + "'[" + column.replace("]", "]]") + "]"
    if item.get("filterType") == 1:
        operator, values = item.get("operator"), item.get("values")
        if operator == "All":
            return None
        if operator not in {"In", "NotIn"} or not isinstance(values, list) or len(values) > 1000:
            raise _invalid()
        value_set = "{" + ",".join(literal(value) for value in values) + "}"
        if operator == "In":
            return f"KEEPFILTERS(TREATAS({value_set}, {field}))"
        return f"KEEPFILTERS(FILTER(ALL({field}), NOT ({field} IN {value_set})))"
    if item.get("filterType") == 0:
        conditions = item.get("conditions")
        logic = item.get("logicalOperator", "And")
        if (
            logic not in {"And", "Or"}
            or not isinstance(conditions, list)
            or not 1 <= len(conditions) <= 2
        ):
            raise _invalid()
        ops = {
            "Is": "=",
            "IsNot": "<>",
            "GreaterThan": ">",
            "GreaterThanOrEqual": ">=",
            "LessThan": "<",
            "LessThanOrEqual": "<=",
        }
        clauses = []
        for condition in conditions:
            if not isinstance(condition, dict):
                raise _invalid()
            operator = condition.get("operator")
            if operator in {"IsBlank", "IsNotBlank"}:
                clauses.append(("NOT " if operator == "IsNotBlank" else "") + f"ISBLANK({field})")
            elif operator in ops:
                clauses.append(f"{field} {ops[operator]} {literal(condition.get('value'))}")
            else:
                raise _invalid()
        return (
            f"KEEPFILTERS(FILTER(ALL({field}), "
            + (" && " if logic == "And" else " || ").join(f"({c})" for c in clauses)
            + "))"
        )
    raise _invalid()


def validate_context(context: ReportContext) -> None:
    if context.mode == "model":
        return
    if context.unsupported:
        raise _invalid()
    for item in context.filters:
        filter_expression(item)


def _masked_dax(query: str) -> str:
    token = (
        r'"(?:""|[^"])*"|\'(?:\'\'|[^\'])*\'|\[(?:\]\]|[^\]])*\]|//[^\n]*|--[^\n]*|/\*[\s\S]*?\*/'
    )
    return re.sub(token, lambda match: " " * len(match[0]), query)


def scoped_dax(query: str, context: ReportContext | None) -> str:
    if len(query) > 50_000:
        raise AppError("POWER_BI_QUERY_INVALID", "The analytical query is too large.", 422)
    masked = _masked_dax(query)
    evaluate = list(re.finditer(r"\bEVALUATE\b", masked, re.I))
    if len(evaluate) != 1 or re.search(
        r"\b(?:CREATE|ALTER|DROP|DELETE|INSERT|UPDATE)\b", masked, re.I
    ):
        raise AppError("POWER_BI_QUERY_INVALID", "Use one read-only DAX EVALUATE query.", 422)
    if context is None or context.mode == "model":
        return query
    validate_context(context)
    filters = [expression for item in context.filters if (expression := filter_expression(item))]
    if not filters:
        return query
    start = evaluate[0].end()
    orders = list(re.finditer(r"\bORDER\s+BY\b", masked[start:], re.I))
    end = start + orders[-1].start() if orders else len(query)
    expression = query[start:end].strip().rstrip(";")
    return (
        query[:start]
        + " CALCULATETABLE(\n"
        + expression
        + ",\n"
        + ",\n".join(filters)
        + "\n) "
        + query[end:]
    )


def context_for_prompt(context: ReportContext | None) -> str:
    return (
        json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
        if context
        else "No live report view attached. Use explicit question scope and report metadata."
    )
