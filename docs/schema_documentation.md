# Retail Sales Database Schema

This document provides the schema context for the NL-to-SQL agents to generate accurate queries.

## Tables Overview

### 1. amazon_sales
Main sales transaction table with order-level data from Amazon marketplace.

| Column | Type | Description | Example Values |
|--------|------|-------------|----------------|
| index | INTEGER | Row index | 0, 1, 2 |
| Order ID | VARCHAR | Unique order identifier | 405-8078784-5731545 |
| Date | DATE | Order date (auto-parsed by DuckDB) | 2022-04-30 |
| Status | VARCHAR | Order status | Shipped, Cancelled, Pending, Shipped - Delivered to Buyer |
| Fulfilment | VARCHAR | Fulfillment type | Merchant, Amazon |
| Sales Channel | VARCHAR | Sales platform | Amazon.in |
| ship-service-level | VARCHAR | Shipping speed | Standard, Expedited |
| Style | VARCHAR | Product style code | SET389, JNE3781 |
| SKU | VARCHAR | Stock keeping unit | SET389-KR-NP-S |
| Category | VARCHAR | Product category | Set, kurta, Western Dress, Blouse |
| Size | VARCHAR | Product size | S, M, L, XL, XXL, 3XL, Free |
| ASIN | VARCHAR | Amazon Standard Identification Number | B09KXVBD7Z |
| Courier Status | VARCHAR | Shipping carrier status | Shipped, Cancelled, Unshipped |
| Qty | INTEGER | Quantity ordered | 0, 1, 2, 3 |
| currency | VARCHAR | Transaction currency | INR |
| Amount | DOUBLE | Order amount in INR | 647.62, 406.0, 329.0 |
| ship-city | VARCHAR | Delivery city | MUMBAI, BENGALURU, DELHI |
| ship-state | VARCHAR | Delivery state (region) | MAHARASHTRA, KARNATAKA, DELHI |
| ship-postal-code | DOUBLE | Postal/PIN code | 400081.0, 560085.0 |
| ship-country | VARCHAR | Delivery country | IN |
| promotion-ids | VARCHAR | Applied promotion identifiers | Amazon PLCC Free-Financing... |
| B2B | BOOLEAN | Business-to-business order flag | True, False |
| fulfilled-by | VARCHAR | Fulfillment handler | Easy Ship |

**Key Metrics**:
- Total Orders: ~128,000+
- Date Range: March 31 - June 29, 2022 (Q2 2022)
- Revenue Column: `Amount`
- Geographic Columns: `ship-state`, `ship-city`

**Important**: Data only covers Q2 2022. Queries for Q3 2022 or later will return no results.

---

### 2. international_sales
International customer sales transactions.

| Column | Type | Description | Example Values |
|--------|------|-------------|----------------|
| DATE | VARCHAR | Sale date (MM-DD-YY) | 06-05-21 |
| Months | VARCHAR | Month-Year period | Jun-21 |
| CUSTOMER | VARCHAR | Customer name | REVATHY LOGANATHAN |
| Style | VARCHAR | Product style | MEN5004, MEN5009 |
| SKU | VARCHAR | Stock keeping unit | MEN5004-KR-L |
| Size | VARCHAR | Product size | L, XL, XXL |
| PCS | DOUBLE | Number of pieces | 1.00 |
| RATE | DOUBLE | Unit rate | 616.56 |
| GROSS AMT | DOUBLE | Gross amount | 617.00 |

---

### 3. pricing
Product pricing data across multiple e-commerce marketplaces.

| Column | Type | Description |
|--------|------|-------------|
| Sku | VARCHAR | Stock keeping unit |
| Style Id | VARCHAR | Style identifier |
| Catalog | VARCHAR | Product catalog name |
| Category | VARCHAR | Product category |
| Weight | DOUBLE | Product weight (kg) |
| TP | DOUBLE | Transfer price (cost) |
| MRP Old | DOUBLE | Original MRP |
| Final MRP Old | DOUBLE | Final old MRP |
| Ajio MRP | DOUBLE | Price on Ajio marketplace |
| Amazon MRP | DOUBLE | Price on Amazon |
| Amazon FBA MRP | DOUBLE | Amazon FBA price |
| Flipkart MRP | DOUBLE | Price on Flipkart |
| Limeroad MRP | DOUBLE | Price on Limeroad |
| Myntra MRP | DOUBLE | Price on Myntra |
| Paytm MRP | DOUBLE | Price on Paytm |
| Snapdeal MRP | DOUBLE | Price on Snapdeal |

---

### 4. inventory
Current stock/inventory levels by SKU.

| Column | Type | Description |
|--------|------|-------------|
| SKU Code | VARCHAR | SKU identifier |
| Design No. | VARCHAR | Design number |
| Stock | DOUBLE | Current stock level |
| Category | VARCHAR | Product category |
| Size | VARCHAR | Product size |
| Color | VARCHAR | Product color |

---

## Common Query Patterns

### Revenue Analysis

```sql
-- Total revenue
SELECT SUM(Amount) as total_revenue FROM amazon_sales

-- Revenue by category
SELECT Category, SUM(Amount) as revenue
FROM amazon_sales
GROUP BY Category
ORDER BY revenue DESC

-- Monthly revenue trend (Date is already DATE type)
SELECT
    strftime('%Y-%m', Date) as month,
    SUM(Amount) as revenue
FROM amazon_sales
GROUP BY month
ORDER BY month
```

### Order Analysis

```sql
-- Orders by status
SELECT Status, COUNT(*) as order_count
FROM amazon_sales
GROUP BY Status

-- Average order value
SELECT AVG(Amount) as avg_order_value FROM amazon_sales WHERE Amount > 0

-- Orders by fulfillment type
SELECT Fulfilment, COUNT(*) as orders, SUM(Amount) as revenue
FROM amazon_sales
GROUP BY Fulfilment
```

### Regional Analysis

```sql
-- Top states by revenue
SELECT "ship-state" as state, SUM(Amount) as revenue
FROM amazon_sales
GROUP BY "ship-state"
ORDER BY revenue DESC
LIMIT 10

-- B2B vs B2C comparison
SELECT B2B, COUNT(*) as orders, SUM(Amount) as revenue
FROM amazon_sales
GROUP BY B2B
```

### Product Analysis

```sql
-- Top categories
SELECT Category, COUNT(*) as orders, SUM(Amount) as revenue
FROM amazon_sales
GROUP BY Category
ORDER BY revenue DESC

-- Size distribution
SELECT Size, COUNT(*) as orders
FROM amazon_sales
GROUP BY Size
ORDER BY orders DESC
```

---

## DuckDB-Specific Notes

### Date Handling
DuckDB's `read_csv_auto` automatically parses the Date column as DATE type.
```sql
-- Date column is already DATE type - no parsing needed
SELECT Date FROM amazon_sales WHERE Date >= '2022-04-01'

-- Extract year/month/quarter
SELECT
    year(Date) as year,
    month(Date) as month,
    quarter(Date) as quarter
FROM amazon_sales

-- Date range in the data: 2022-03-31 to 2022-06-29
-- Use this to filter queries appropriately
```

### Column Names with Special Characters
Some columns have hyphens in names. Use double quotes:
```sql
SELECT "ship-state", "ship-city" FROM amazon_sales
```

### NULL Handling
- `Amount` may be NULL for cancelled orders
- Use `COALESCE(Amount, 0)` for aggregations
- Filter with `WHERE Amount IS NOT NULL AND Amount > 0`

---

## Business Glossary

| Term | Definition |
|------|------------|
| **Revenue** | Sum of `Amount` column |
| **AOV** | Average Order Value = SUM(Amount) / COUNT(orders) |
| **YoY** | Year-over-Year comparison |
| **QoQ** | Quarter-over-Quarter comparison |
| **B2B** | Business-to-Business orders (B2B = True) |
| **B2C** | Business-to-Consumer orders (B2B = False) |
| **FBA** | Fulfillment by Amazon |
| **MRP** | Maximum Retail Price |
| **TP** | Transfer Price (internal cost) |
