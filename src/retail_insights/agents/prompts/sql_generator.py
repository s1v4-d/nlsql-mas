"""SQL Generator agent prompt templates.

This module defines prompts for natural language to SQL translation,
with schema context injection and self-correction support for retries.
"""

from datetime import datetime

SQL_GENERATOR_SYSTEM_PROMPT = """You are an expert DuckDB SQL analyst for a retail sales database.

Your task is to translate natural language questions into accurate, efficient SQL queries.

## Important Rules

### SELECT Only
- Generate ONLY SELECT statements
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, or any DDL/DML

### LIMIT Clause
- ALWAYS include a LIMIT clause
- Default: LIMIT 100 for exploration queries
- Use user-specified limit if mentioned (e.g., "top 5" → LIMIT 5)

### Column Names
- Use EXACT column names from the schema (case-sensitive)
- Quote columns with special characters: "ship-state", "Courier Status"
- Never invent column names not in the schema

### Date Handling (CRITICAL)
- Dates in the data use format: MM-DD-YY (e.g., "04-30-22")
- Parse string dates: strptime(Date, '%m-%d-%y')
- Use DATE_TRUNC for period comparisons
- Current date reference: {current_date}

### Aggregation Rules
- "total", "sum" → SUM()
- "average", "mean", "per" → AVG()
- "count", "how many" → COUNT()
- "top N" → ORDER BY ... DESC LIMIT N
- Always GROUP BY non-aggregated columns in SELECT

### NULL Handling
- Filter NULLs when doing aggregations
- Use COALESCE for default values
- Use NULLIF to prevent division by zero

## Available Schema
{schema_context}

## Examples

### Simple Aggregation
Question: "What is the total revenue?"
SQL: SELECT SUM(Amount) as total_revenue FROM amazon_sales LIMIT 1

### Top N with Grouping
Question: "What are the top 5 categories by revenue?"
SQL: SELECT Category, SUM(Amount) as revenue FROM amazon_sales GROUP BY Category ORDER BY revenue DESC LIMIT 5

### Date Filtering
Question: "Show sales from April 2022"
SQL: SELECT * FROM amazon_sales WHERE strptime(Date, '%m-%d-%y') >= '2022-04-01' AND strptime(Date, '%m-%d-%y') < '2022-05-01' LIMIT 100

### Conditional Aggregation
Question: "Compare shipped vs cancelled orders"
SQL: SELECT Status, COUNT(*) as order_count, SUM(Amount) as revenue FROM amazon_sales WHERE Status IN ('Shipped', 'Cancelled') GROUP BY Status LIMIT 10

### Filtering with Special Column Names
Question: "Show orders by state"
SQL: SELECT "ship-state", COUNT(*) as order_count FROM amazon_sales GROUP BY "ship-state" ORDER BY order_count DESC LIMIT 20
"""

SQL_GENERATOR_USER_PROMPT = """## User Question
{user_query}

{retry_context}

Generate a SQL query that accurately answers this question. Provide:
1. The complete SQL query
2. A brief explanation of what it does
3. List of tables and columns used
4. Any assumptions you made"""


def format_sql_generator_prompt(
    user_query: str,
    schema_context: str,
    *,
    validation_errors: list[str] | None = None,
    previous_sql: str | None = None,
    current_date: str | None = None,
) -> tuple[str, str]:
    """Format the SQL generator prompt with context.

    Args:
        user_query: The natural language question from the user.
        schema_context: Schema documentation for available tables/columns.
        validation_errors: List of errors from previous attempt (for retry).
        previous_sql: Previously generated SQL that failed (for retry).
        current_date: Current date string for temporal context.

    Returns:
        Tuple of (system_prompt, user_prompt) for LLM invocation.
    """
    if current_date is None:
        current_date = datetime.now().strftime("%Y-%m-%d")

    system = SQL_GENERATOR_SYSTEM_PROMPT.format(
        schema_context=schema_context or "No schema context available.",
        current_date=current_date,
    )

    # Build retry context if this is a retry attempt
    retry_context = ""
    if validation_errors and previous_sql:
        error_list = "\n".join(f"- {err}" for err in validation_errors)
        retry_context = f"""
## Previous Attempt Failed
Your previous SQL query had errors:

{error_list}

Previous SQL:
```sql
{previous_sql}
```

Please fix these issues in your new query. Common fixes:
- Check column names match schema exactly (case-sensitive)
- Use strptime() for date parsing, not TO_DATE
- Ensure all referenced tables exist
- Add missing GROUP BY for non-aggregated columns
"""

    user = SQL_GENERATOR_USER_PROMPT.format(
        user_query=user_query,
        retry_context=retry_context,
    )

    return system, user


# Few-shot examples for improved SQL generation
SQL_GENERATOR_FEW_SHOT_EXAMPLES = [
    {
        "question": "What were total sales last month?",
        "sql": """SELECT SUM(Amount) as total_revenue
FROM amazon_sales
WHERE strptime(Date, '%m-%d-%y') >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
  AND strptime(Date, '%m-%d-%y') < DATE_TRUNC('month', CURRENT_DATE)
LIMIT 1""",
        "explanation": "Calculates total sales amount for the previous calendar month using date truncation.",
        "tables_used": ["amazon_sales"],
        "columns_used": ["Amount", "Date"],
    },
    {
        "question": "Top 5 categories by sales",
        "sql": """SELECT Category, SUM(Amount) as revenue
FROM amazon_sales
GROUP BY Category
ORDER BY revenue DESC
LIMIT 5""",
        "explanation": "Aggregates sales by category and returns the top 5 highest revenue categories.",
        "tables_used": ["amazon_sales"],
        "columns_used": ["Category", "Amount"],
    },
    {
        "question": "Compare B2B vs B2C orders",
        "sql": """SELECT B2B, COUNT(*) as order_count, SUM(Amount) as revenue, AVG(Amount) as avg_order_value
FROM amazon_sales
GROUP BY B2B
LIMIT 10""",
        "explanation": "Compares B2B and B2C segments by order count, total revenue, and average order value.",
        "tables_used": ["amazon_sales"],
        "columns_used": ["B2B", "Amount"],
    },
    {
        "question": "Show orders from Maharashtra",
        "sql": """SELECT "Order ID", Date, Amount, Status, "ship-city"
FROM amazon_sales
WHERE "ship-state" = 'MAHARASHTRA'
ORDER BY Amount DESC
LIMIT 100""",
        "explanation": "Retrieves orders shipped to Maharashtra state, sorted by amount.",
        "tables_used": ["amazon_sales"],
        "columns_used": ["Order ID", "Date", "Amount", "Status", "ship-city", "ship-state"],
    },
    {
        "question": "What is the cancellation rate?",
        "sql": """SELECT
    COUNT(*) FILTER (WHERE Status = 'Cancelled') as cancelled_count,
    COUNT(*) as total_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE Status = 'Cancelled') / NULLIF(COUNT(*), 0), 2) as cancellation_rate
FROM amazon_sales
LIMIT 1""",
        "explanation": "Calculates overall cancellation rate using conditional aggregation and NULLIF to prevent division by zero.",
        "tables_used": ["amazon_sales"],
        "columns_used": ["Status"],
    },
    {
        "question": "Average order value by fulfillment type",
        "sql": """SELECT Fulfilment, AVG(Amount) as avg_order_value, COUNT(*) as order_count
FROM amazon_sales
WHERE Amount IS NOT NULL
GROUP BY Fulfilment
ORDER BY avg_order_value DESC
LIMIT 10""",
        "explanation": "Computes average order value grouped by fulfillment type (Merchant vs Amazon), excluding null amounts.",
        "tables_used": ["amazon_sales"],
        "columns_used": ["Fulfilment", "Amount"],
    },
]


# Column name mappings for common business terms
BUSINESS_TERM_MAPPINGS = {
    # Revenue/Sales terms
    "revenue": "Amount",
    "sales": "Amount",
    "order_value": "Amount",
    "total": "Amount",
    # Location terms
    "region": "ship-state",
    "state": "ship-state",
    "city": "ship-city",
    "location": "ship-state",
    # Order identifiers
    "order": "Order ID",
    "order_id": "Order ID",
    "sku": "SKU",
    "product": "SKU",
    # Quantity
    "quantity": "Qty",
    "units": "Qty",
    # Status
    "order_status": "Status",
    "courier_status": "Courier Status",
    # Fulfillment
    "fulfillment": "Fulfilment",
    "shipped_by": "Fulfilment",
}
