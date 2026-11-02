"""Build data/olist.duckdb from the raw Olist CSVs.

Raw tables are loaded as-is apart from column renames (typo fixes) and the
`products.category_en` column. Business rules live in docs/olist_dictionary.md,
not in views, so the model has to apply them itself.
"""
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
RAW = ROOT / CFG["paths"]["raw_olist"]
DB = ROOT / CFG["paths"]["olist_db"]

TABLES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}

# Explicit types for keys and timestamps so auto-detection can't guess wrong
# (zip prefixes keep leading zeros, timestamps are real TIMESTAMPs).
TYPES = {
    "orders": {"order_purchase_timestamp": "TIMESTAMP", "order_approved_at": "TIMESTAMP",
               "order_delivered_carrier_date": "TIMESTAMP", "order_delivered_customer_date": "TIMESTAMP",
               "order_estimated_delivery_date": "TIMESTAMP"},
    "order_items": {"shipping_limit_date": "TIMESTAMP", "price": "DOUBLE", "freight_value": "DOUBLE"},
    "payments": {"payment_value": "DOUBLE"},
    "reviews": {"review_creation_date": "TIMESTAMP", "review_answer_timestamp": "TIMESTAMP"},
    "customers": {"customer_zip_code_prefix": "VARCHAR"},
    "sellers": {"seller_zip_code_prefix": "VARCHAR"},
    "geolocation": {"geolocation_zip_code_prefix": "VARCHAR"},
}

RENAMES = {
    "products": {"product_name_lenght": "product_name_length",
                 "product_description_lenght": "product_description_length"},
}

REGIONS = {
    "North": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "Northeast": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Center-West": ["DF", "GO", "MT", "MS"],
    "Southeast": ["ES", "MG", "RJ", "SP"],
    "South": ["PR", "RS", "SC"],
}


def build() -> None:
    DB.unlink(missing_ok=True)
    con = duckdb.connect(str(DB))
    for table, fname in TABLES.items():
        path = RAW / fname
        types = TYPES.get(table, {})
        type_arg = f", types={types!r}" if types else ""
        # encoding utf-8 strips the BOM on the translation file's first header
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv('{path}', header=true{type_arg})")
        for old, new in RENAMES.get(table, {}).items():
            con.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")

    # Guard against a BOM-prefixed first column in the translation file.
    cols = [r[0] for r in con.execute("DESCRIBE category_translation").fetchall()]
    if cols[0] != "product_category_name":
        con.execute(f'ALTER TABLE category_translation RENAME COLUMN "{cols[0]}" TO product_category_name')

    con.execute("CREATE TABLE regions (state VARCHAR PRIMARY KEY, region VARCHAR)")
    con.executemany("INSERT INTO regions VALUES (?, ?)",
                    [(s, r) for r, states in REGIONS.items() for s in states])

    con.execute("ALTER TABLE products ADD COLUMN category_en VARCHAR")
    con.execute("""
        UPDATE products p SET category_en = COALESCE(
            (SELECT t.product_category_name_english FROM category_translation t
             WHERE t.product_category_name = p.product_category_name),
            p.product_category_name)
    """)
    con.close()
    print(f"built {DB}")


if __name__ == "__main__":
    build()
