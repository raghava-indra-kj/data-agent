"""Conservative SQL Server SELECT policy, independent of driver execution."""

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from data_agent_mcp.domain.data_sources.models import DataSource, TableIdentifier
from data_agent_mcp.domain.queries import OperationError

# Unknown/UDF functions are deliberately rejected: SELECT is not necessarily free
# of external side effects. Expand this set only for reviewed built-in functions.
FUNCTIONS = {
    "ABS",
    "AVG",
    "CEIL",
    "CEILING",
    "FLOOR",
    "ROUND",
    "POWER",
    "SQRT",
    "SUM",
    "MIN",
    "MAX",
    "COUNT",
    "COUNT_BIG",
    "COALESCE",
    "NULLIF",
    "ISNULL",
    "IF",
    "CAST",
    "TRY_CAST",
    "CONVERT",
    "TRY_CONVERT",
    "UPPER",
    "LOWER",
    "TRIM",
    "LTRIM",
    "RTRIM",
    "LENGTH",
    "LEN",
    "SUBSTRING",
    "CONCAT",
    "CONCAT_WS",
    "REPLACE",
    "LEFT",
    "RIGHT",
    "CHARINDEX",
    "DATEADD",
    "DATE_ADD",
    "DATEDIFF",
    "DATE_DIFF",
    "DATEPART",
    "DATE_PART",
    "DATENAME",
    "YEAR",
    "MONTH",
    "DAY",
    "GETDATE",
    "CURRENT_TIMESTAMP",
    "CURRENT_DATE",
    "CURRENT_DATETIME",
    "ROW_NUMBER",
    "RANK",
    "DENSE_RANK",
    "LAG",
    "LEAD",
    "FIRST_VALUE",
    "LAST_VALUE",
    "NTILE",
    "STDDEV",
    "STDDEV_SAMP",
    "VARIANCE",
    "VAR_SAMP",
    "APPROX_COUNT_DISTINCT",
    "STRING_AGG",
    "GROUP_CONCAT",
    "CASE",
    "EXTRACT",
    "DATEFROMPARTS",
    "EOMONTH",
    "TS_OR_DS_TO_DATE",
    "TIME_TO_STR",
    "STR_TO_TIME",
}


def validate_select(
    sql: str, source: DataSource, parameters: list, max_rows: int, max_characters: int = 30_000
) -> str:
    if not sql.strip() or len(sql) > max_characters:
        raise OperationError("INVALID_SQL", f"SQL must contain 1 to {max_characters} characters.")
    try:
        statements = sqlglot.parse(sql, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)
    except Exception:
        raise OperationError("INVALID_SQL", "SQL could not be parsed as supported T-SQL.") from None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise OperationError(
            "READ_ONLY_REQUIRED", "Only one SELECT or SELECT UNION statement is permitted."
        )
    tree = statements[0]
    blocked = {
        "Into",
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Create",
        "Drop",
        "Alter",
        "Command",
        "Execute",
        "NextValueFor",
        "Lock",
        "Transaction",
    }
    for node in tree.walk():
        if isinstance(node, exp.Table) and node.args.get("hints"):
            raise OperationError(
                "READ_ONLY_REQUIRED", "Table hints are not permitted in read-only queries."
            )
        if type(node).__name__ in blocked:
            raise OperationError(
                "READ_ONLY_REQUIRED",
                "Write operations, locks and sequence operations are not permitted.",
            )
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            if name not in FUNCTIONS:
                raise OperationError(
                    "FUNCTION_NOT_ALLOWED",
                    f"Function {name[:80]} is outside the supported built-in function allowlist.",
                )
        if isinstance(node, exp.Dot) and isinstance(node.expression, exp.Func):
            raise OperationError(
                "FUNCTION_NOT_ALLOWED", "Schema-qualified functions are not permitted."
            )
    if sum(1 for _ in tree.find_all(exp.Placeholder)) != len(parameters):
        raise OperationError(
            "PARAMETER_MISMATCH", "The number of ? placeholders must match parameters."
        )
    for scope in traverse_scope(tree):
        for _, (_, selected) in scope.selected_sources.items():
            if not isinstance(selected, exp.Table):
                continue
            if selected.catalog or not selected.db or not isinstance(selected.this, exp.Identifier):
                raise OperationError(
                    "TABLE_SCOPE_REQUIRED",
                    "Use two-part schema.table names; cross-database/server references and table functions are forbidden.",
                )
            if not source.permits(TableIdentifier(selected.db, selected.name)):
                raise OperationError(
                    "TABLE_NOT_ALLOWED",
                    "A referenced table is outside the configured access scope.",
                )
    # Rewrite the outer limit. Never expand an existing smaller literal TOP.
    limit = tree.args.get("limit")
    if limit:
        expression = limit.expression
        if (
            not isinstance(expression, exp.Literal)
            or not expression.is_int
            or any(limit.args.get(k) for k in ("percent", "with_ties", "limit_options"))
        ):
            raise OperationError(
                "UNSUPPORTED_LIMIT", "Use a literal TOP count without PERCENT or WITH TIES."
            )
        max_rows = min(max_rows + 1, max(0, int(expression.this)))
    else:
        max_rows += 1
    return tree.limit(max_rows).sql(dialect="tsql")
