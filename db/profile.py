"""Quality checks and trap evidence for data/olist.duckdb. Prints counts; asserts key integrity."""
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
con = duckdb.connect(str(ROOT / CFG["paths"]["olist_db"]), read_only=True)


def q(sql):
    return con.execute(sql).fetchall()


def one(sql):
    return q(sql)[0][0]


print("== Row counts")
for (t,) in q("SELECT table_name FROM information_schema.tables ORDER BY 1"):
    print(f"  {t:22s} {one(f'SELECT COUNT(*) FROM {t}'):>10,}")

print("\n== Key integrity")
checks = {
    "order_items -> orders": "SELECT COUNT(*) FROM order_items i LEFT JOIN orders o USING (order_id) WHERE o.order_id IS NULL",
    "payments -> orders": "SELECT COUNT(*) FROM payments p LEFT JOIN orders o USING (order_id) WHERE o.order_id IS NULL",
    "reviews -> orders": "SELECT COUNT(*) FROM reviews r LEFT JOIN orders o USING (order_id) WHERE o.order_id IS NULL",
    "orders -> customers": "SELECT COUNT(*) FROM orders o LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL",
    "order_items -> products": "SELECT COUNT(*) FROM order_items i LEFT JOIN products p USING (product_id) WHERE p.product_id IS NULL",
    "order_items -> sellers": "SELECT COUNT(*) FROM order_items i LEFT JOIN sellers s USING (seller_id) WHERE s.seller_id IS NULL",
    "customer states in regions": "SELECT COUNT(*) FROM customers c LEFT JOIN regions r ON r.state = c.customer_state WHERE r.state IS NULL",
    "seller states in regions": "SELECT COUNT(*) FROM sellers s LEFT JOIN regions r ON r.state = s.seller_state WHERE r.state IS NULL",
}
for name, sql in checks.items():
    n = one(sql)
    print(f"  {name:28s} orphans={n}")
    assert n == 0, name
assert one("SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders") == 0, "duplicate order_id"

print("\n== NULL rates (orders)")
for col in ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date"]:
    print(f"  {col:32s} {one(f'SELECT AVG(({col} IS NULL)::INT) FROM orders'):.3%}")

print("\n== Trap evidence")
traps = {
    "customer_id rows": "SELECT COUNT(DISTINCT customer_id) FROM customers",
    "distinct customer_unique_id": "SELECT COUNT(DISTINCT customer_unique_id) FROM customers",
    "orders with >1 seller": "SELECT COUNT(*) FROM (SELECT order_id FROM order_items GROUP BY 1 HAVING COUNT(DISTINCT seller_id) > 1)",
    "orders with >1 item": "SELECT COUNT(*) FROM (SELECT order_id FROM order_items GROUP BY 1 HAVING COUNT(*) > 1)",
    "orders with >1 payment row": "SELECT COUNT(*) FROM (SELECT order_id FROM payments GROUP BY 1 HAVING COUNT(*) > 1)",
    "duplicate review_id values": "SELECT COUNT(*) FROM (SELECT review_id FROM reviews GROUP BY 1 HAVING COUNT(*) > 1)",
    "orders with >1 review": "SELECT COUNT(*) FROM (SELECT order_id FROM reviews GROUP BY 1 HAVING COUNT(*) > 1)",
    "avg geolocation rows per zip": "SELECT AVG(n) FROM (SELECT COUNT(*) n FROM geolocation GROUP BY geolocation_zip_code_prefix)",
    "categories with no translation": "SELECT COUNT(DISTINCT product_category_name) FROM products p WHERE product_category_name IS NOT NULL AND NOT EXISTS (SELECT 1 FROM category_translation t WHERE t.product_category_name = p.product_category_name)",
    "products with NULL category": "SELECT COUNT(*) FROM products WHERE product_category_name IS NULL",
}
for name, sql in traps.items():
    v = one(sql)
    print(f"  {name:32s} {v:,.2f}" if isinstance(v, float) else f"  {name:32s} {v:,}")

print("\n== Order statuses")
for s, n in q("SELECT order_status, COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC"):
    print(f"  {s:12s} {n:>7,}")

print("\n== Payment types")
for s, n in q("SELECT payment_type, COUNT(*) FROM payments GROUP BY 1 ORDER BY 2 DESC"):
    print(f"  {s:12s} {n:>7,}")

print("\n== Orders per month (purchase date)")
for m, n in q("SELECT strftime(order_purchase_timestamp, '%Y-%m'), COUNT(*) FROM orders GROUP BY 1 ORDER BY 1"):
    print(f"  {m} {n:>6,}")
