"""Sample CSV data for E2E testing.

This module generates sample retail sales data matching the production schema
for use in end-to-end tests with DuckDB.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

CATEGORIES = ["Set", "kurta", "Western Dress", "Top", "Blouse", "Ethnic Dress", "Bottom"]
STATES = ["MAHARASHTRA", "KARNATAKA", "DELHI", "TAMIL NADU", "TELANGANA", "GUJARAT", "WEST BENGAL"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "Free"]
STATUSES = ["Shipped", "Delivered", "Cancelled", "Returned"]


def generate_sample_data(
    output_path: Path,
    num_rows: int = 100,
    seed: int = 42,
) -> Path:
    """Generate sample retail sales CSV data for testing.

    Args:
        output_path: Directory to write the CSV file.
        num_rows: Number of rows to generate.
        seed: Random seed for reproducibility.

    Returns:
        Path to the generated CSV file.
    """
    rng = Random(seed)
    output_file = output_path / "sample_sales.csv"

    base_date = datetime(2022, 1, 1)

    fieldnames = [
        "Order ID",
        "Date",
        "Status",
        "Fulfilment",
        "Category",
        "Size",
        "Qty",
        "Amount",
        "ship-city",
        "ship-state",
        "B2B",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i in range(num_rows):
            days_offset = rng.randint(0, 180)
            order_date = base_date + timedelta(days=days_offset)
            category = rng.choice(CATEGORIES)
            state = rng.choice(STATES)

            # Generate amount based on category (for realistic grouping patterns)
            base_amounts = {
                "Set": 1500,
                "kurta": 800,
                "Western Dress": 1200,
                "Top": 400,
                "Blouse": 350,
                "Ethnic Dress": 1800,
                "Bottom": 600,
            }
            base_amount = base_amounts.get(category, 500)
            amount = round(base_amount * (0.5 + rng.random()), 2)
            qty = rng.randint(1, 5)

            writer.writerow(
                {
                    "Order ID": f"ORD-E2E-{i + 1:05d}",
                    "Date": order_date.strftime("%m-%d-%y"),
                    "Status": rng.choice(STATUSES),
                    "Fulfilment": rng.choice(["Amazon", "Merchant"]),
                    "Category": category,
                    "Size": rng.choice(SIZES),
                    "Qty": qty,
                    "Amount": amount,
                    "ship-city": f"{state}_CITY_{rng.randint(1, 5)}",
                    "ship-state": state,
                    "B2B": rng.choice(["TRUE", "FALSE"]),
                }
            )

    return output_file


def generate_edge_case_data(output_path: Path) -> Path:
    """Generate edge case data for testing NULL handling, Unicode, etc.

    Args:
        output_path: Directory to write the CSV file.

    Returns:
        Path to the generated CSV file.
    """
    output_file = output_path / "edge_cases.csv"

    fieldnames = [
        "Order ID",
        "Date",
        "Status",
        "Fulfilment",
        "Category",
        "Size",
        "Qty",
        "Amount",
        "ship-city",
        "ship-state",
        "B2B",
    ]

    edge_cases = [
        # Normal row
        {
            "Order ID": "ORD-EDGE-001",
            "Date": "01-01-22",
            "Status": "Shipped",
            "Fulfilment": "Amazon",
            "Category": "kurta",
            "Size": "M",
            "Qty": 1,
            "Amount": 500.00,
            "ship-city": "Mumbai",
            "ship-state": "MAHARASHTRA",
            "B2B": "FALSE",
        },
        # Empty string city (CSV empty field)
        {
            "Order ID": "ORD-EDGE-002",
            "Date": "01-02-22",
            "Status": "Delivered",
            "Fulfilment": "Merchant",
            "Category": "Set",
            "Size": "L",
            "Qty": 2,
            "Amount": 1200.50,
            "ship-city": "",
            "ship-state": "KARNATAKA",
            "B2B": "TRUE",
        },
        # Cancelled order with zero amount
        {
            "Order ID": "ORD-EDGE-003",
            "Date": "01-03-22",
            "Status": "Cancelled",
            "Fulfilment": "Amazon",
            "Category": "Top",
            "Size": "XS",
            "Qty": 1,
            "Amount": 0.0,
            "ship-city": "Delhi",
            "ship-state": "DELHI",
            "B2B": "FALSE",
        },
        # Large quantity
        {
            "Order ID": "ORD-EDGE-004",
            "Date": "01-04-22",
            "Status": "Shipped",
            "Fulfilment": "Amazon",
            "Category": "Blouse",
            "Size": "Free",
            "Qty": 100,
            "Amount": 35000.00,
            "ship-city": "Chennai",
            "ship-state": "TAMIL NADU",
            "B2B": "TRUE",
        },
        # Decimal precision edge case
        {
            "Order ID": "ORD-EDGE-005",
            "Date": "01-05-22",
            "Status": "Delivered",
            "Fulfilment": "Merchant",
            "Category": "Western Dress",
            "Size": "M",
            "Qty": 1,
            "Amount": 999.99,
            "ship-city": "Hyderabad",
            "ship-state": "TELANGANA",
            "B2B": "FALSE",
        },
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(edge_cases)

    return output_file
