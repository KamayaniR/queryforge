"""Hand-written test items (Kam's questions; gold SQL written to the data dictionary).

Test only, never trained on. Writes bench/out/test_handwritten.jsonl and, with
--freeze, test_handwritten.sha256. Interpretations are recorded in `notes`.
"""
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.generate import is_degenerate, run  # noqa: E402
from bench.templates import ACTIVE_WINDOW, DAYS, DELIVERED, LATE, VALID  # noqa: E402
from contracts import BenchItem  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
OUT = ROOT / CFG["paths"]["bench_out"]


def pf(start, end):
    return f"o.order_purchase_timestamp >= DATE '{start}' AND o.order_purchase_timestamp < DATE '{end}'"


Y17, Y18 = pf("2017-01-01", "2018-01-01"), pf("2018-01-01", "2019-01-01")
GMV_JOIN = "FROM order_items i JOIN orders o ON o.order_id = i.order_id"

# (question, category, difficulty, gold_sql, notes)
ITEMS = [
    # ---- Everyday
    ("how many orders got cancelled in 2017", "simple", "easy",
     f"SELECT COUNT(*) FROM orders o WHERE o.order_status = 'canceled' AND {Y17}",
     "status canceled; period by purchase date"),
    ("hey can u pull order counts by month for jan thru jun 2018?", "date", "easy",
     f"SELECT strftime(o.order_purchase_timestamp, '%Y-%m') AS month, COUNT(*) FROM orders o "
     f"WHERE {pf('2018-01-01', '2018-07-01')} GROUP BY 1 ORDER BY 1",
     "all statuses; months as YYYY-MM"),
    ("which state do most of our customers live in", "gotcha", "easy",
     "SELECT customer_state FROM customers GROUP BY 1 ORDER BY COUNT(DISTINCT customer_unique_id) DESC LIMIT 1",
     "customers = distinct customer_unique_id"),
    ("quick one, how many sellers r in RJ", "simple", "easy",
     "SELECT COUNT(*) FROM sellers WHERE seller_state = 'RJ'", ""),
    ("on avg how many items are in a delivered order", "gotcha", "medium",
     f"SELECT COUNT(*) * 1.0 / COUNT(DISTINCT i.order_id) {GMV_JOIN} WHERE o.order_status = 'delivered'",
     "items per order over orders with status delivered"),
    ("whats the top 5 categories by items sold this yr (2018)", "join", "medium",
     f"SELECT p.category_en {GMV_JOIN} JOIN products p ON p.product_id = i.product_id "
     f"WHERE {Y18} AND p.category_en IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 5",
     "items = order_items rows; all statuses (no named rule)"),
    ("what % of orders paid w credit card at least once", "gotcha", "medium",
     "SELECT 100.0 * COUNT(DISTINCT CASE WHEN p.payment_type = 'credit_card' THEN o.order_id END) / COUNT(DISTINCT o.order_id) "
     "FROM orders o LEFT JOIN payments p ON p.order_id = o.order_id",
     "percentage asked, so 0-100; all orders, all time"),
    ("how many 5 star reviews did we get in 2017?", "simple", "medium",
     f"SELECT COUNT(*) FROM reviews r JOIN orders o ON o.order_id = r.order_id WHERE r.review_score = 5 AND {Y17}",
     "no date named, so period by order purchase date (dictionary rule)"),
    # ---- Business rules
    ("total sales for 2017?", "business_rule", "easy",
     f"SELECT SUM(i.price) {GMV_JOIN} WHERE {VALID} AND {Y17}", "sales = GMV"),
    ("can i get revenue for last month pls", "business_rule", "easy",
     f"SELECT SUM(i.price) {GMV_JOIN} WHERE {VALID} AND {pf('2018-07-01', '2018-08-01')}",
     "last month = 2018-07; revenue = GMV"),
    ("need GMV split by region for fiscal Q2 FY18", "business_rule", "medium",
     f"SELECT r.region, SUM(i.price) {GMV_JOIN} JOIN customers c ON c.customer_id = o.customer_id "
     f"JOIN regions r ON r.state = c.customer_state WHERE {VALID} AND {pf('2018-05-01', '2018-08-01')} GROUP BY 1",
     "FY18 Q2 = May-Jul 2018; customer region (default)"),
    ("late delivery rate for nov 2017 orders?", "business_rule", "medium",
     f"SELECT AVG(CASE WHEN {LATE} THEN 1.0 ELSE 0.0 END) FROM orders o WHERE {DELIVERED} AND {pf('2017-11-01', '2017-12-01')}",
     "fraction; delivered orders with a delivery date"),
    ("hey how many active sellers in SP rn", "business_rule", "medium",
     f"SELECT COUNT(DISTINCT i.seller_id) {GMV_JOIN} JOIN sellers s ON s.seller_id = i.seller_id "
     f"WHERE {VALID} AND {ACTIVE_WINDOW} AND s.seller_state = 'SP'", "active window 2018-06-02..2018-08-31"),
    ("what % of customers r repeat customers", "business_rule", "medium",
     "WITH c AS (SELECT cu.customer_unique_id, COUNT(DISTINCT o.order_id) AS n FROM orders o "
     f"JOIN customers cu ON cu.customer_id = o.customer_id WHERE {VALID} GROUP BY 1) "
     "SELECT 100.0 * AVG(CASE WHEN n >= 2 THEN 1.0 ELSE 0.0 END) FROM c",
     "percentage; all time; among customers with a valid order (same as the repeat-share template)"),
    ("how many low ratings came in last qtr (going by review date)", "business_rule", "medium",
     "SELECT COUNT(*) FROM reviews r WHERE r.review_score <= 2 AND r.review_creation_date >= DATE '2018-04-01' "
     "AND r.review_creation_date < DATE '2018-07-01'", "last quarter = 2018 Q2; review_creation_date"),
    ("avg delivery time in days for orders from march 2018", "business_rule", "easy",
     f"SELECT AVG({DAYS}) FROM orders o WHERE {DELIVERED} AND {pf('2018-03-01', '2018-04-01')}", ""),
    # ---- Multi-step / harder
    ("which seller state had the worst late rate in 2017? only states w 100+ delivered orders pls", "business_rule", "hard",
     f"WITH t AS (SELECT DISTINCT o.order_id, s.seller_state, CASE WHEN {LATE} THEN 1.0 ELSE 0.0 END AS late "
     f"{GMV_JOIN} JOIN sellers s ON s.seller_id = i.seller_id WHERE {DELIVERED} AND {Y17}) "
     "SELECT seller_state FROM t GROUP BY 1 HAVING COUNT(*) >= 100 ORDER BY AVG(late) DESC LIMIT 1",
     "per distinct (order, seller state)"),
    ("can u do month over month GMV growth % for 2018 thru aug", "date", "hard",
     f"WITH m AS (SELECT strftime(o.order_purchase_timestamp, '%Y-%m') AS month, SUM(i.price) AS gmv {GMV_JOIN} "
     f"WHERE {VALID} AND {pf('2017-12-01', '2018-09-01')} GROUP BY 1), "
     "g AS (SELECT month, 100.0 * (gmv - LAG(gmv) OVER (ORDER BY month)) / LAG(gmv) OVER (ORDER BY month) AS growth FROM m) "
     "SELECT month, growth FROM g WHERE month >= '2018-01' ORDER BY month",
     "percent; Jan 2018 compared with Dec 2017; 8 rows"),
    ("top 3 categories by GMV per region in 2017", "join", "hard",
     f"WITH t AS (SELECT r.region, p.category_en, SUM(i.price) AS gmv {GMV_JOIN} "
     "JOIN customers c ON c.customer_id = o.customer_id JOIN regions r ON r.state = c.customer_state "
     f"JOIN products p ON p.product_id = i.product_id WHERE {VALID} AND {Y17} AND p.category_en IS NOT NULL GROUP BY 1, 2), "
     "k AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY gmv DESC) AS rn FROM t) "
     "SELECT region, category_en FROM k WHERE rn <= 3", "customer region; 15 rows"),
    ("who were our top 10 sellers by revenue in FY17", "date", "hard",
     f"SELECT i.seller_id {GMV_JOIN} WHERE {VALID} AND {pf('2017-02-01', '2018-02-01')} "
     "GROUP BY 1 ORDER BY SUM(i.price) DESC LIMIT 10", "FY17 = 2017-02-01..2018-01-31; revenue = GMV"),
    ("do late orders get worse reviews? avg score late vs on time", "business_rule", "hard",
     f"WITH d AS (SELECT o.order_id, CASE WHEN {LATE} THEN 1 ELSE 0 END AS late FROM orders o WHERE {DELIVERED}) "
     "SELECT AVG(CASE WHEN d.late = 1 THEN r.review_score END) AS late_avg, "
     "AVG(CASE WHEN d.late = 0 THEN r.review_score END) AS on_time_avg FROM reviews r JOIN d ON d.order_id = r.order_id",
     "one row, two values; delivered orders with a delivery date; averaged over review rows"),
    ("how many customers placed their first order in 2017 and then ordered again in 2018", "gotcha", "hard",
     "WITH f AS (SELECT c.customer_unique_id, MIN(o.order_purchase_timestamp) AS first_ts, "
     f"MAX(CASE WHEN {Y18} THEN 1 ELSE 0 END) AS in18 FROM orders o JOIN customers c ON c.customer_id = o.customer_id GROUP BY 1) "
     "SELECT COUNT(*) FROM f WHERE first_ts >= DATE '2017-01-01' AND first_ts < DATE '2018-01-01' AND in18 = 1",
     "customer_unique_id; all statuses"),
    ("what % of 2017 GMV came from just the top 20 sellers", "business_rule", "hard",
     f"WITH s AS (SELECT i.seller_id, SUM(i.price) AS gmv {GMV_JOIN} WHERE {VALID} AND {Y17} GROUP BY 1) "
     "SELECT 100.0 * (SELECT SUM(gmv) FROM (SELECT gmv FROM s ORDER BY gmv DESC LIMIT 20)) / SUM(gmv) FROM s",
     "percentage"),
    ("for stuff shipped by SP sellers, which 5 customer states wait the longest on avg", "join", "hard",
     f"WITH t AS (SELECT DISTINCT o.order_id, c.customer_state, {DAYS} AS d {GMV_JOIN} "
     "JOIN sellers s ON s.seller_id = i.seller_id JOIN customers c ON c.customer_id = o.customer_id "
     f"WHERE {DELIVERED} AND s.seller_state = 'SP') SELECT customer_state FROM t GROUP BY 1 ORDER BY AVG(d) DESC LIMIT 5",
     "delivery time per distinct order; all time"),
    # ---- Traps
    ("how many unique customers ordered in 2018", "gotcha", "easy",
     f"SELECT COUNT(DISTINCT c.customer_unique_id) FROM orders o JOIN customers c ON c.customer_id = o.customer_id WHERE {Y18}",
     "overlaps the unique_customers_period template"),
    ("avg amount paid per order when a voucher was used", "gotcha", "medium",
     "WITH t AS (SELECT p.order_id, SUM(p.payment_value) AS paid FROM payments p WHERE p.order_id IN "
     "(SELECT order_id FROM payments WHERE payment_type = 'voucher') GROUP BY 1) SELECT AVG(paid) FROM t",
     "total paid per order (all payment rows) for orders with a voucher payment"),
    ("whats the avg review score per order for MG sellers", "gotcha", "hard",
     "WITH per AS (SELECT r.order_id, AVG(r.review_score) AS sc FROM reviews r WHERE r.order_id IN "
     "(SELECT i.order_id FROM order_items i JOIN sellers s ON s.seller_id = i.seller_id WHERE s.seller_state = 'MG') "
     "GROUP BY 1) SELECT AVG(sc) FROM per",
     "'per order': average each order's reviews first, then average over orders"),
    ("how many orders had items from more than 1 seller", "gotcha", "medium",
     "SELECT COUNT(*) FROM (SELECT order_id FROM order_items GROUP BY 1 HAVING COUNT(DISTINCT seller_id) > 1)", "all time"),
    ("total health & beauty sales 2017?", "business_rule", "easy",
     f"SELECT SUM(i.price) {GMV_JOIN} JOIN products p ON p.product_id = i.product_id "
     f"WHERE {VALID} AND {Y17} AND p.category_en = 'health_beauty'", "sales = GMV"),
    ("avg delivery days for orders placed in 2018", "business_rule", "easy",
     f"SELECT AVG({DAYS}) FROM orders o WHERE {DELIVERED} AND {Y18}", ""),
]


def main(freeze=False):
    con = duckdb.connect(str(ROOT / CFG["paths"]["olist_db"]), read_only=True)
    rows = []
    for k, (q, cat, diff, sql, notes) in enumerate(ITEMS):
        cols, res = run(con, sql)
        assert not is_degenerate(res), f"degenerate gold for #{k + 1}: {q}"
        rows.append(BenchItem(id=f"hw_{k + 1:03d}", question=q, category=cat, difficulty=diff, source="handwritten",
                              split="test", expected_action="answer", gold_sql=sql, gold_columns=cols,
                              gold_result=res, order_matters=False, notes=notes).model_dump())
        shown = res if len(res) <= 3 else res[:3] + [f"... {len(res)} rows"]
        print(f"{k + 1:2d}. {q}\n    -> {shown}")
    path = OUT / "test_handwritten.jsonl"
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if freeze:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        (OUT / "test_handwritten.sha256").write_text(sha + "\n")
        print(f"FROZEN test_handwritten.jsonl sha256={sha}")


if __name__ == "__main__":
    if "--freeze" in sys.argv and (OUT / "test_handwritten.sha256").exists():
        sys.exit("test_handwritten.sha256 exists: already frozen.")
    main("--freeze" in sys.argv)
