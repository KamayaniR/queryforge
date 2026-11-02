"""Question templates with gold SQL (CLAUDE.md section 8).

Each template = phrasings x fills. A fill is a dict of parameter values used to
format both the phrasings and the gold SQL. generate.py runs every gold SQL.

Top-N templates use two extra placeholders so generate.py can detect ties at
the cut-off: `{_m}` (empty in gold; ", <metric>" in the tie check) and `{_lim}`.
"""
from dataclasses import dataclass, field

VALID = "o.order_status NOT IN ('canceled', 'unavailable')"
ACTIVE_WINDOW = ("o.order_purchase_timestamp >= DATE '2018-06-02' "
                 "AND o.order_purchase_timestamp < DATE '2018-09-01'")
LATE = "CAST(o.order_delivered_customer_date AS DATE) > CAST(o.order_estimated_delivery_date AS DATE)"
DELIVERED = "o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL"
DAYS = "date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date)"

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def _period(label, short, start, end):
    pf = (f"o.order_purchase_timestamp >= DATE '{start}' "
          f"AND o.order_purchase_timestamp < DATE '{end}'")
    return {"label": label, "short": short, "start": start, "end": end, "pf": pf}


def _month(y, m):
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return _period(f"{MONTH_NAMES[m - 1]} {y}", f"{MONTH_NAMES[m - 1][:3].lower()} {y}",
                   f"{y}-{m:02d}-01", f"{ny}-{nm:02d}-01")


MONTHS = [_month(y, m) for y in (2017, 2018) for m in range(1, 13) if (y, m) <= (2018, 8)]
YEARS = [_period("2017", "2017", "2017-01-01", "2018-01-01"),
         _period("2018", "2018", "2018-01-01", "2019-01-01")]
QUARTERS = [_period(f"Q{q} {y}", f"q{q} {y}", f"{y}-{3 * q - 2:02d}-01",
                    f"{y + (q == 4)}-{(3 * q + 1) % 12 or 12:02d}-01".replace("-13-", "-01-"))
            for y in (2017, 2018) for q in (1, 2, 3, 4) if (y, q) <= (2018, 2)]
PERIODS = YEARS + QUARTERS
FISCAL = [
    _period("fiscal Q1 FY2017", "FY17 Q1", "2017-02-01", "2017-05-01"),
    _period("fiscal Q2 FY2017", "FY17 Q2", "2017-05-01", "2017-08-01"),
    _period("fiscal Q3 FY2017", "FY17 Q3", "2017-08-01", "2017-11-01"),
    _period("fiscal Q4 FY2017", "FY17 Q4", "2017-11-01", "2018-02-01"),
    _period("fiscal Q1 FY2018", "FY18 Q1", "2018-02-01", "2018-05-01"),
    _period("fiscal Q2 FY2018", "FY18 Q2", "2018-05-01", "2018-08-01"),
    _period("fiscal Q3 FY2018", "FY18 Q3", "2018-08-01", "2018-11-01"),
]
RELATIVE = [
    _period("this month", "this month", "2018-08-01", "2018-09-01"),
    _period("last month", "last month", "2018-07-01", "2018-08-01"),
    _period("last quarter", "last quarter", "2018-04-01", "2018-07-01"),
    _period("this year", "this year", "2018-01-01", "2019-01-01"),
    _period("last year", "last year", "2017-01-01", "2018-01-01"),
]
LAST_N = [_period(f"the last {n} days", f"last {n} days",
                  f"{__import__('datetime').date(2018, 8, 31) - __import__('datetime').timedelta(days=n - 1)}",
                  "2018-09-01") for n in (7, 14, 30, 60, 90)]

STATE_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}
SELLER_STATES = ["SP", "PR", "MG", "SC", "RJ", "RS", "GO", "DF", "ES", "BA", "PE", "CE", "MT", "MS"]
CUST_STATES = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "ES", "GO", "PE", "CE"]
CATS = ["bed_bath_table", "health_beauty", "sports_leisure", "furniture_decor", "computers_accessories",
        "housewares", "watches_gifts", "telephony", "garden_tools", "auto", "toys", "cool_stuff",
        "perfumery", "baby", "electronics", "stationery", "fashion_bags_accessories", "pet_shop",
        "office_furniture", "consoles_games", "luggage_accessories", "construction_tools_construction",
        "home_appliances", "musical_instruments", "small_appliances"]
CITIES = ["sao paulo", "rio de janeiro", "belo horizonte", "brasilia", "curitiba", "campinas",
          "porto alegre", "salvador", "guarulhos", "sao bernardo do campo", "niteroi", "santo andre",
          "osasco", "santos", "goiania"]
PTYPES = {"credit_card": "credit card", "boleto": "boleto", "voucher": "voucher", "debit_card": "debit card"}
STATUSES = ["delivered", "canceled", "shipped"]
REGIONS = ["North", "Northeast", "Center-West", "Southeast", "South"]


def _state(s):
    return {"state": s, "state_name": STATE_NAMES[s]}


def _cat(c):
    return {"cat": c, "catn": c.replace("_", " ")}


def _cross(*lists):
    out = [{}]
    for lst in lists:
        out = [{**a, **b} for a in out for b in lst]
    return out


def _p(periods, prefix=""):
    """Period dicts with keys prefixed (so two periods can coexist in one fill)."""
    return [{f"{prefix}{k}": v for k, v in p.items()} for p in periods]


@dataclass
class Template:
    id: str
    category: str
    difficulty: str
    phrasings: list[str]
    fills: list[dict]
    sql: str
    explain: str
    assumptions: list[str] = field(default_factory=list)
    tie_metric: str | None = None  # metric expression for top-N tie check
    n_key: str | None = None       # fill key holding N for top-N templates
    order_matters: bool = False


T = Template
TEMPLATES: list[Template] = [
    # ---------------- simple ----------------
    T("orders_month", "simple", "easy",
      ["How many orders were placed in {label}?",
       "hey can u pull the total order count for {short}",
       "number of orders in {label}?",
       "Need the count of all orders purchased during {label} for a deck"],
      _p(MONTHS),
      "SELECT COUNT(*) AS orders FROM orders o WHERE {pf}",
      "Counted all orders purchased in {label}, any status.",
      ["Period filtered on order_purchase_timestamp", "All order statuses included"]),
    T("status_orders_month", "simple", "easy",
      ["How many orders placed in {label} have status {status}?",
       "count of {status} orders from {short}?",
       "{label}: how many orders ended up {status}?"],
      _cross(_p(MONTHS), [{"status": s} for s in STATUSES]),
      "SELECT COUNT(*) AS orders FROM orders o WHERE o.order_status = '{status}' AND {pf}",
      "Counted orders purchased in {label} with order_status '{status}'.",
      ["Period filtered on order_purchase_timestamp"]),
    T("sellers_state", "simple", "easy",
      ["How many sellers are based in {state_name}?",
       "seller count for {state}?",
       "how many sellers do we have in {state_name} ({state})"],
      [_state(s) for s in STATE_NAMES],
      "SELECT COUNT(*) AS sellers FROM sellers WHERE seller_state = '{state}'",
      "Counted sellers whose seller_state is {state}.", []),
    T("products_category", "simple", "easy",
      ["How many products are listed in the {catn} category?",
       "number of products in category {cat}?",
       "how many {catn} products are in the catalog"],
      [_cat(c) for c in CATS],
      "SELECT COUNT(*) AS products FROM products WHERE category_en = '{cat}'",
      "Counted products whose English category is {cat}.", []),
    T("avg_item_price_category", "simple", "medium",
      ["What's the average item price in the {catn} category?",
       "avg price per item sold for {cat}?",
       "hey whats the mean item price for {catn} items"],
      [_cat(c) for c in CATS],
      "SELECT AVG(i.price) AS avg_price FROM order_items i JOIN products p ON p.product_id = i.product_id "
      "WHERE p.category_en = '{cat}'",
      "Averaged order_items.price over all items in category {cat}.",
      ["All order items included (no status filter)", "Freight excluded"]),
    T("reviews_written_month", "simple", "medium",
      ["How many reviews were created in {label}?",
       "count of reviews submitted in {short} (by review creation date)",
       "number of reviews written during {label}?"],
      _p(MONTHS),
      "SELECT COUNT(*) AS reviews FROM reviews r WHERE r.review_creation_date >= DATE '{start}' "
      "AND r.review_creation_date < DATE '{end}'",
      "Counted review rows with review_creation_date in {label}.",
      ["Period filtered on review_creation_date, since the question is about when reviews were written"]),

    # ---------------- join ----------------
    T("ptype_orders_month", "join", "medium",
      ["How many orders placed in {label} were paid at least partly by {ptn}?",
       "number of orders from {short} that used {ptn}",
       "how many {label} orders had a {ptn} payment?"],
      _cross(_p(MONTHS), [{"ptype": k, "ptn": v} for k, v in PTYPES.items()]),
      "SELECT COUNT(DISTINCT o.order_id) AS orders FROM orders o JOIN payments p ON p.order_id = o.order_id "
      "WHERE p.payment_type = '{ptype}' AND {pf}",
      "Counted distinct orders purchased in {label} with at least one {ptype} payment.",
      ["Distinct orders, since an order can have several payments"]),
    T("top_cat_gmv", "join", "medium",
      ["What are the top {n} categories by GMV in {label}?",
       "which {n} product categories brought in the most revenue in {label}?",
       "hey can u list the top {n} categories by sales for {short}"],
      _cross(_p(PERIODS), [{"n": n} for n in (3, 5, 10)]),
      "SELECT p.category_en{_m} FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN products p ON p.product_id = i.product_id WHERE " + VALID + " AND {pf} AND p.category_en IS NOT NULL "
      "GROUP BY 1 ORDER BY SUM(i.price) DESC LIMIT {_lim}",
      "Ranked English categories by GMV (sum of item price on valid orders) in {label}.",
      ["GMV = sum of item price on valid orders, excluding freight", "Period filtered on order_purchase_timestamp"],
      tie_metric="SUM(i.price)", n_key="n"),
    T("top_sellers_delivered_state", "join", "medium",
      ["Which {n} sellers in {state_name} have the most delivered orders?",
       "top {n} {state} sellers by number of delivered orders",
       "list the {n} sellers based in {state_name} with the most delivered orders"],
      _cross([_state(s) for s in SELLER_STATES[:9]], [{"n": n} for n in (3, 5)]),
      "SELECT i.seller_id{_m} FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN sellers s ON s.seller_id = i.seller_id WHERE o.order_status = 'delivered' AND s.seller_state = '{state}' "
      "GROUP BY 1 ORDER BY COUNT(DISTINCT o.order_id) DESC LIMIT {_lim}",
      "Ranked sellers in {state} by distinct delivered orders.",
      ["Seller location from seller_state", "Distinct orders per seller"],
      tie_metric="COUNT(DISTINCT o.order_id)", n_key="n"),
    T("sellers_category_period", "join", "medium",
      ["How many different sellers sold {catn} products in {label}?",
       "number of distinct sellers with {cat} sales in {short}",
       "how many sellers sold something in {catn} during {label}?"],
      _cross(_p(YEARS), [_cat(c) for c in CATS]),
      "SELECT COUNT(DISTINCT i.seller_id) AS sellers FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN products p ON p.product_id = i.product_id WHERE p.category_en = '{cat}' AND {pf}",
      "Counted distinct sellers with order items in {cat} on orders purchased in {label}.",
      ["All order statuses included", "Period filtered on order_purchase_timestamp"]),

    # ---------------- date ----------------
    T("gmv_by_month_range", "date", "medium",
      ["Show GMV by month from {a_label} through {b_label}.",
       "monthly revenue {a_short} to {b_short} pls",
       "can I get a month-by-month GMV breakdown for {a_label} to {b_label}?"],
      [{**{f"a_{k}": v for k, v in MONTHS[i].items()}, **{f"b_{k}": v for k, v in MONTHS[i + 2].items()}}
       for i in range(len(MONTHS) - 2)],
      "SELECT strftime(o.order_purchase_timestamp, '%Y-%m') AS month, SUM(i.price) AS gmv FROM order_items i "
      "JOIN orders o ON o.order_id = i.order_id WHERE " + VALID +
      " AND o.order_purchase_timestamp >= DATE '{a_start}' AND o.order_purchase_timestamp < DATE '{b_end}' "
      "GROUP BY 1 ORDER BY 1",
      "Summed item price on valid orders per purchase month, {a_label} to {b_label}.",
      ["GMV = sum of item price on valid orders", "Months as YYYY-MM by purchase date"]),
    T("fq_valid_orders", "date", "medium",
      ["How many valid orders were there in {label}?",
       "valid order count for {short}?",
       "number of non-canceled, available orders in {label}"],
      _p(FISCAL),
      "SELECT COUNT(*) AS valid_orders FROM orders o WHERE " + VALID + " AND {pf}",
      "Counted valid orders purchased in {label} ({start} to {end}, exclusive).",
      ["Fiscal year starts Feb 1", "Valid = status not canceled/unavailable"]),
    T("growth_orders_mom", "date", "hard",
      ["What was the month-over-month growth rate in order count from {a_label} to {b_label}?",
       "how much did orders grow from {a_short} to {b_short}? (as a growth rate)",
       "order growth {a_label} -> {b_label}, relative change please"],
      [{**{f"a_{k}": v for k, v in MONTHS[i].items()}, **{f"b_{k}": v for k, v in MONTHS[i + 1].items()}}
       for i in range(len(MONTHS) - 1)],
      "WITH m AS (SELECT SUM(CASE WHEN o.order_purchase_timestamp >= DATE '{a_start}' AND "
      "o.order_purchase_timestamp < DATE '{a_end}' THEN 1 ELSE 0 END) AS prev, "
      "SUM(CASE WHEN o.order_purchase_timestamp >= DATE '{b_start}' AND o.order_purchase_timestamp < DATE '{b_end}' "
      "THEN 1 ELSE 0 END) AS cur FROM orders o) SELECT (cur - prev) * 1.0 / NULLIF(prev, 0) AS growth FROM m",
      "Computed (orders in {b_label} - orders in {a_label}) / orders in {a_label}.",
      ["All order statuses", "Growth returned as a fraction"]),
    T("last_n_days_metric", "date", "medium",
      ["What's the {metric} for {label}?",
       "{metric} over {short}?",
       "quick one: {metric} in {label}"],
      None,  # filled below (metric x period)
      "{msql}",
      "Computed {metric} for {start} to 2018-08-31 inclusive.",
      ["Relative to the as-of date 2018-08-31"]),
    T("relative_named_metric", "date", "medium",
      ["What was the {metric} {label}?",
       "can u pull {metric} for {short}",
       "{metric}, {label}?"],
      None,
      "{msql}",
      "Computed {metric} for {label} ({start} to {end}, exclusive).",
      ["Relative to the as-of date 2018-08-31", "Calendar periods"]),
    T("weekday_month", "date", "medium",
      ["Which day of the week had the most orders in {label}?",
       "busiest weekday for orders in {short}?",
       "what weekday saw the most orders during {label}"],
      [{**p, "n": 1} for p in _p(MONTHS)],
      "SELECT dayname(o.order_purchase_timestamp) AS weekday{_m} FROM orders o WHERE {pf} "
      "GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT {_lim}",
      "Grouped orders purchased in {label} by weekday and took the largest.",
      ["All order statuses", "Weekday of purchase timestamp"],
      tie_metric="COUNT(*)", n_key="n"),

    # ---------------- business_rule ----------------
    T("gmv_month", "business_rule", "easy",
      ["What was GMV in {label}?",
       "revenue for {short}?",
       "hey what were total sales in {label}"],
      _p(MONTHS),
      "SELECT SUM(i.price) AS gmv FROM order_items i JOIN orders o ON o.order_id = i.order_id WHERE " + VALID +
      " AND {pf}",
      "Summed item price on valid orders purchased in {label}.",
      ["GMV = item price on valid orders, freight excluded"]),
    T("freight_month", "business_rule", "medium",
      ["What was freight revenue in {label}?",
       "total freight we charged in {short}?",
       "how much freight revenue came in during {label}"],
      _p(MONTHS),
      "SELECT SUM(i.freight_value) AS freight FROM order_items i JOIN orders o ON o.order_id = i.order_id WHERE "
      + VALID + " AND {pf}",
      "Summed freight_value on valid orders purchased in {label}.",
      ["Valid orders only"]),
    T("gmv_state_year", "business_rule", "medium",
      ["What was GMV from customers in {state_name} in {label}?",
       "revenue from {state} customers in {short}?",
       "how much did customers in {state_name} spend in {label} (GMV)?"],
      _cross(_p(YEARS), [_state(s) for s in CUST_STATES]),
      "SELECT SUM(i.price) AS gmv FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN customers c ON c.customer_id = o.customer_id WHERE " + VALID + " AND c.customer_state = '{state}' AND {pf}",
      "Summed item price on valid orders from customers in {state}, {label}.",
      ["Customer state from customers.customer_state", "GMV excludes freight"]),
    T("gmv_seller_region_period", "business_rule", "medium",
      ["Break down GMV by seller region for {label}.",
       "revenue per seller region in {short}?",
       "how much GMV did each seller region generate in {label}"],
      _p(PERIODS + MONTHS),
      "SELECT r.region, SUM(i.price) AS gmv FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN sellers s ON s.seller_id = i.seller_id JOIN regions r ON r.state = s.seller_state WHERE " + VALID +
      " AND {pf} GROUP BY 1",
      "Summed item price on valid orders by seller region, {label}.",
      ["Seller region, as asked", "GMV excludes freight"]),
    T("fq_gmv_region", "business_rule", "hard",
      ["What was GMV from {region} customers in {label}?",
       "revenue from the {region} region in {short}?",
       "{label} GMV for customers in the {region}"],
      _cross(_p(FISCAL), [{"region": r} for r in REGIONS]),
      "SELECT SUM(i.price) AS gmv FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN customers c ON c.customer_id = o.customer_id JOIN regions r ON r.state = c.customer_state WHERE "
      + VALID + " AND r.region = '{region}' AND {pf}",
      "Summed item price on valid orders from {region} customers in {label}.",
      ["Fiscal year starts Feb 1", "Customer region"]),
    T("late_rate_region_month", "business_rule", "medium",
      ["What's the late delivery rate by region for {label}?",
       "whats the late delivery rate by customer region for {short}",
       "late rate per region, {label} orders"],
      _p(MONTHS),
      "SELECT r.region, AVG(CASE WHEN " + LATE + " THEN 1.0 ELSE 0.0 END) AS late_rate FROM orders o "
      "JOIN customers c ON c.customer_id = o.customer_id JOIN regions r ON r.state = c.customer_state WHERE "
      + DELIVERED + " AND {pf} GROUP BY 1",
      "Share of delivered orders (purchased in {label}) delivered after the estimated date, by customer region.",
      ["Customer region", "Late compares dates, not times", "Only delivered orders with a delivery date"]),
    T("late_rate_state_period", "business_rule", "medium",
      ["What was the late delivery rate for customers in {state_name} in {label}?",
       "late rate for {state} in {short}?",
       "what % of {state_name} orders from {label} arrived late? (as a rate)"],
      _cross(_p(PERIODS), [_state(s) for s in CUST_STATES]),
      "SELECT AVG(CASE WHEN " + LATE + " THEN 1.0 ELSE 0.0 END) AS late_rate FROM orders o "
      "JOIN customers c ON c.customer_id = o.customer_id WHERE " + DELIVERED +
      " AND c.customer_state = '{state}' AND {pf}",
      "Share of delivered {state} orders purchased in {label} that arrived after the estimate.",
      ["Late compares dates", "Only delivered orders with a delivery date"]),
    T("active_sellers_state", "business_rule", "medium",
      ["How many active sellers are in {state_name}?",
       "active seller count for {state}?",
       "how many sellers in {state_name} are currently active"],
      [_state(s) for s in SELLER_STATES],
      "SELECT COUNT(DISTINCT i.seller_id) AS active_sellers FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN sellers s ON s.seller_id = i.seller_id WHERE " + VALID + " AND " + ACTIVE_WINDOW +
      " AND s.seller_state = '{state}'",
      "Counted sellers in {state} with a valid order item purchased 2018-06-02 to 2018-08-31.",
      ["Active = valid order item in the 90 days ending 2018-08-31"]),
    T("active_sellers_category", "business_rule", "medium",
      ["How many active sellers sell {catn} products?",
       "active sellers in {cat}?",
       "number of currently active sellers in the {catn} category"],
      [_cat(c) for c in CATS],
      "SELECT COUNT(DISTINCT i.seller_id) AS active_sellers FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN products p ON p.product_id = i.product_id WHERE " + VALID + " AND " + ACTIVE_WINDOW +
      " AND p.category_en = '{cat}'",
      "Counted sellers with a valid {cat} order item purchased 2018-06-02 to 2018-08-31.",
      ["Active = valid order item in the 90 days ending 2018-08-31",
       "Counted the seller as active in the category via that category's items"]),
    T("repeat_share_period", "business_rule", "hard",
      ["What share of customers in {label} were repeat customers?",
       "repeat customer rate for {short}?",
       "of the customers who ordered in {label}, what fraction placed 2+ valid orders?"],
      _p(PERIODS),
      "WITH c AS (SELECT cu.customer_unique_id, COUNT(DISTINCT o.order_id) AS n FROM orders o "
      "JOIN customers cu ON cu.customer_id = o.customer_id WHERE " + VALID + " AND {pf} GROUP BY 1) "
      "SELECT AVG(CASE WHEN n >= 2 THEN 1.0 ELSE 0.0 END) AS repeat_share FROM c",
      "Among customer_unique_ids with a valid order in {label}, the share with 2+ valid orders in that period.",
      ["Customer = customer_unique_id", "Repeat = 2+ valid orders within the period"]),
    T("repeat_count_period", "business_rule", "medium",
      ["How many repeat customers did we have in {label}?",
       "number of repeat customers in {short}?",
       "count customers with 2 or more valid orders in {label}"],
      _p(PERIODS + MONTHS),
      "SELECT COUNT(*) AS repeat_customers FROM (SELECT cu.customer_unique_id FROM orders o "
      "JOIN customers cu ON cu.customer_id = o.customer_id WHERE " + VALID + " AND {pf} GROUP BY 1 "
      "HAVING COUNT(DISTINCT o.order_id) >= 2)",
      "Counted customer_unique_ids with 2+ valid orders purchased in {label}.",
      ["Customer = customer_unique_id", "Repeat counted within the period"]),
    T("avg_delivery_region_period", "business_rule", "medium",
      ["What's the average delivery time in days by region for {label}?",
       "avg delivery days per customer region, {short}",
       "how long did deliveries take on average in each region in {label}?"],
      _p(PERIODS + MONTHS),
      "SELECT r.region, AVG(" + DAYS + ") AS avg_days FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
      "JOIN regions r ON r.state = c.customer_state WHERE " + DELIVERED + " AND {pf} GROUP BY 1",
      "Averaged days from purchase to customer delivery by customer region, {label}.",
      ["Only delivered orders with a delivery date", "Customer region"]),
    T("low_rating_share_category", "business_rule", "medium",
      ["What share of reviews for {catn} orders are low ratings?",
       "low rating rate for {cat}?",
       "what fraction of {catn} reviews are 1 or 2 stars?"],
      [_cat(c) for c in CATS],
      "SELECT AVG(CASE WHEN r.review_score <= 2 THEN 1.0 ELSE 0.0 END) AS low_share FROM reviews r "
      "WHERE r.order_id IN (SELECT i.order_id FROM order_items i JOIN products p ON p.product_id = i.product_id "
      "WHERE p.category_en = '{cat}')",
      "Share of reviews (on orders containing {cat} items) with score <= 2.",
      ["Low rating = score <= 2", "Orders filtered with IN to avoid duplicating reviews"]),
    T("low_rating_count_month", "business_rule", "easy",
      ["How many low-rating reviews were there for orders placed in {label}?",
       "count of 1-2 star reviews on {short} orders",
       "number of low ratings for {label} orders?"],
      _p(MONTHS),
      "SELECT COUNT(*) AS low_reviews FROM reviews r JOIN orders o ON o.order_id = r.order_id "
      "WHERE r.review_score <= 2 AND {pf}",
      "Counted reviews with score <= 2 on orders purchased in {label}.",
      ["Low rating = score <= 2", "Period by order purchase date"]),

    # ---------------- gotcha ----------------
    T("unique_customers_period", "gotcha", "medium",
      ["How many unique customers ordered in {label}?",
       "number of distinct customers who bought something in {short}",
       "how many customers placed orders in {label}?"],
      _p(PERIODS + MONTHS),
      "SELECT COUNT(DISTINCT cu.customer_unique_id) AS customers FROM orders o "
      "JOIN customers cu ON cu.customer_id = o.customer_id WHERE {pf}",
      "Counted distinct customer_unique_id with an order purchased in {label}.",
      ["Customer = customer_unique_id (customer_id is per order)", "All order statuses"]),
    T("customers_city", "gotcha", "easy",
      ["How many customers are in {city}?",
       "customer count for {city}?",
       "number of customers located in {city}"],
      [{"city": c} for c in CITIES],
      "SELECT COUNT(DISTINCT customer_unique_id) AS customers FROM customers WHERE customer_city = '{city}'",
      "Counted distinct customer_unique_id with customer_city '{city}'.",
      ["Customer = customer_unique_id"]),
    T("customers_state", "gotcha", "easy",
      ["How many customers do we have in {state_name}?",
       "customer count in {state}?",
       "number of customers based in {state_name}"],
      [_state(s) for s in CUST_STATES],
      "SELECT COUNT(DISTINCT customer_unique_id) AS customers FROM customers WHERE customer_state = '{state}'",
      "Counted distinct customer_unique_id with customer_state {state}.",
      ["Customer = customer_unique_id"]),
    T("top_states_customers_period", "gotcha", "medium",
      ["Which {n} states had the most customers ordering in {label}?",
       "top {n} states by number of customers in {short}",
       "list the {n} customer states with the most distinct buyers in {label}"],
      _cross(_p(PERIODS), [{"n": n} for n in (3, 5)]),
      "SELECT c.customer_state{_m} FROM orders o JOIN customers c ON c.customer_id = o.customer_id WHERE {pf} "
      "GROUP BY 1 ORDER BY COUNT(DISTINCT c.customer_unique_id) DESC LIMIT {_lim}",
      "Ranked customer states by distinct customer_unique_id ordering in {label}.",
      ["Customer = customer_unique_id"],
      tie_metric="COUNT(DISTINCT c.customer_unique_id)", n_key="n"),
    T("avg_paid_per_order_month", "gotcha", "medium",
      ["What was the average paid amount per order in {label}?",
       "avg amount paid per order for {short}?",
       "on average how much was paid per order in {label}"],
      _p(MONTHS),
      "WITH t AS (SELECT p.order_id, SUM(p.payment_value) AS paid FROM payments p JOIN orders o ON o.order_id = p.order_id "
      "WHERE {pf} GROUP BY 1) SELECT AVG(paid) AS avg_paid FROM t",
      "Summed payments per order, then averaged over orders purchased in {label}.",
      ["Orders can have several payments, so payments are summed per order first", "All order statuses"]),
    T("paid_amount_valid_month", "gotcha", "medium",
      ["What was the total paid amount for valid orders placed in {label}?",
       "sum of payments on valid {short} orders?",
       "how much was paid in total for valid orders in {label}"],
      _p(MONTHS),
      "SELECT SUM(p.payment_value) AS paid FROM payments p JOIN orders o ON o.order_id = p.order_id WHERE "
      + VALID + " AND {pf}",
      "Summed payment_value on valid orders purchased in {label}.",
      ["Paid amount = sum of payment_value", "Not joined to order_items (would duplicate rows)"]),
    T("avg_review_seller_state", "gotcha", "hard",
      ["What's the average review score for orders from sellers in {state_name}?",
       "avg review score for {state} sellers' orders?",
       "how are orders from {state_name}-based sellers rated on average"],
      [_state(s) for s in SELLER_STATES[:9]],
      "SELECT AVG(r.review_score) AS avg_score FROM reviews r WHERE r.order_id IN (SELECT i.order_id FROM order_items i "
      "JOIN sellers s ON s.seller_id = i.seller_id WHERE s.seller_state = '{state}')",
      "Averaged review_score over reviews of orders that include a seller from {state}.",
      ["Orders filtered with IN so multi-item orders don't duplicate reviews"]),
    T("avg_review_category", "gotcha", "medium",
      ["What's the average review score for {catn} orders?",
       "avg rating for orders with {cat} items?",
       "how do customers rate {catn} orders on average"],
      [_cat(c) for c in CATS],
      "SELECT AVG(r.review_score) AS avg_score FROM reviews r WHERE r.order_id IN (SELECT i.order_id FROM order_items i "
      "JOIN products p ON p.product_id = i.product_id WHERE p.category_en = '{cat}')",
      "Averaged review_score over reviews of orders containing {cat} items.",
      ["Orders filtered with IN so multi-item orders don't duplicate reviews"]),
    T("multi_seller_orders_month", "gotcha", "hard",
      ["How many orders placed in {label} had items from more than one seller?",
       "number of multi-seller orders in {short}?",
       "how many {label} orders included 2+ different sellers"],
      _p(MONTHS),
      "SELECT COUNT(*) AS orders FROM (SELECT i.order_id FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "WHERE {pf} GROUP BY 1 HAVING COUNT(DISTINCT i.seller_id) > 1)",
      "Counted orders purchased in {label} whose items come from 2+ distinct sellers.", []),
    T("items_per_order_month", "gotcha", "medium",
      ["What's the average number of items per order in {label}?",
       "avg items per order for {short}?",
       "how many items does an order have on average in {label}"],
      _p(MONTHS),
      "SELECT COUNT(*) * 1.0 / COUNT(DISTINCT i.order_id) AS items_per_order FROM order_items i "
      "JOIN orders o ON o.order_id = i.order_id WHERE {pf}",
      "Divided item rows by distinct orders for orders purchased in {label}.",
      ["Only orders that have items", "All statuses"]),
    T("orders_with_category_month", "gotcha", "medium",
      ["How many orders in {label} included {catn} products?",
       "number of orders with {cat} items in {short}?",
       "how many {label} orders contained at least one {catn} item"],
      [{**m, **_cat(c)} for i, m in enumerate(_p(MONTHS)) for c in CATS[i % 5::5][:2]],
      "SELECT COUNT(DISTINCT i.order_id) AS orders FROM order_items i JOIN orders o ON o.order_id = i.order_id "
      "JOIN products p ON p.product_id = i.product_id WHERE p.category_en = '{cat}' AND {pf}",
      "Counted distinct orders purchased in {label} with at least one {cat} item.",
      ["Distinct orders, since an order can have several items"]),
]

# Metric x period fills for the two relative-date templates.
_METRICS = {
    "order count": "SELECT COUNT(*) AS orders FROM orders o WHERE {pf}",
    "number of valid orders": "SELECT COUNT(*) AS valid_orders FROM orders o WHERE " + VALID + " AND {pf}",
    "GMV": "SELECT SUM(i.price) AS gmv FROM order_items i JOIN orders o ON o.order_id = i.order_id WHERE "
           + VALID + " AND {pf}",
    "number of unique customers": "SELECT COUNT(DISTINCT cu.customer_unique_id) AS customers FROM orders o "
                                  "JOIN customers cu ON cu.customer_id = o.customer_id WHERE {pf}",
}


def _metric_fills(periods):
    return [{**p, "metric": m, "msql": sql.format(pf=p["pf"])} for p in _p(periods) for m, sql in _METRICS.items()]


for _t in TEMPLATES:
    if _t.id == "last_n_days_metric":
        _t.fills = _metric_fills(LAST_N)
    elif _t.id == "relative_named_metric":
        _t.fills = _metric_fills(RELATIVE)

BY_ID = {t.id: t for t in TEMPLATES}
