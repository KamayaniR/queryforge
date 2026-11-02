# Olist data dictionary

Brazilian e-commerce marketplace, orders 2016-09 to 2018-10 (DuckDB). Timestamps are Brazil local time.

## Tables

- **orders**: one row per order. order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date (all TIMESTAMP).
  order_status values: delivered, shipped, canceled, unavailable, invoiced, processing, created, approved.
- **order_items**: one row per item in an order. order_id, order_item_id (1..n within order), product_id, seller_id, shipping_limit_date, price, freight_value. One order can have many items and many sellers.
- **payments**: one row per payment on an order. order_id, payment_sequential, payment_type (credit_card, boleto, voucher, debit_card, not_defined), payment_installments, payment_value. One order can have several payments.
- **reviews**: review_id, order_id, review_score (1-5), review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp. review_id is not unique; some orders have more than one review.
- **customers**: one row per customer_id. customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state (2-letter code).
- **sellers**: seller_id, seller_zip_code_prefix, seller_city, seller_state.
- **products**: product_id, product_category_name (Portuguese), category_en (English name; falls back to Portuguese when untranslated; NULL when the product has no category), product_name_length, product_description_length, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm. (Raw columns `*_lenght` were renamed to `*_length`.)
- **category_translation**: product_category_name, product_category_name_english.
- **geolocation**: geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state. Many rows per zip prefix: aggregate per zip before joining.
- **regions**: state, region (North, Northeast, Center-West, Southeast, South).

Joins: orders.customer_id = customers.customer_id; order_items/payments/reviews.order_id = orders.order_id; order_items.product_id = products.product_id; order_items.seller_id = sellers.seller_id; regions.state = customer_state or seller_state.

## Business rules

| Term | Definition |
|---|---|
| As-of date ("today") | 2018-08-31. Data after it is incomplete. |
| Valid order | order_status NOT IN ('canceled', 'unavailable') |
| GMV / revenue / sales | SUM(order_items.price) over valid orders. Excludes freight. |
| Freight revenue | SUM(order_items.freight_value) over valid orders |
| Paid amount | SUM(payments.payment_value) (all payment rows of the order) |
| Customer | COUNT(DISTINCT customers.customer_unique_id). Never count customer_id. |
| Repeat customer | customer_unique_id with 2 or more valid orders (over all time unless a period is given) |
| Active seller | seller with at least one order_item on a valid order purchased between 2018-06-02 and 2018-08-31 inclusive |
| Late delivery | CAST(order_delivered_customer_date AS DATE) > CAST(order_estimated_delivery_date AS DATE) |
| Late rate | late orders / orders with order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL |
| Delivery time (days) | date_diff('day', order_purchase_timestamp, order_delivered_customer_date), delivered orders with a delivery date only |
| Region | via regions. Customer region (customer_state) unless "seller" is said. |
| Period filter | "in {month/quarter/year}" filters on order_purchase_timestamp unless another date is named |
| Calendar periods | Default. "this month" = 2018-08, "last month" = 2018-07, "this year" = 2018, "last year" = 2017, "last quarter" = 2018 Q2 (Apr-Jun), "last N days" = the N days ending 2018-08-31 inclusive |
| Fiscal year | Only when "fiscal" or "FY" is said. Starts Feb 1: FY2018 = 2018-02-01 to 2019-01-31. Q1 Feb-Apr, Q2 May-Jul, Q3 Aug-Oct, Q4 Nov-Jan. |
| Low rating | review_score <= 2 |
| Average review score | AVG(review_score) over review rows of the qualifying orders (filter orders with IN/EXISTS; do not join through order_items, which duplicates reviews) |
| Category | report category_en |
| Rates and shares | return as a fraction between 0 and 1 unless a percentage is asked for |

## Conventions

- "Orders" counts all orders regardless of status unless the question names a status or says "valid". The same goes for any count or average that is not a named business rule above.
- Answer with the fewest columns that answer the question: for "which"/"top N" questions return the identifying column(s) (e.g. category_en, seller_id, state), plus the metric if useful.
- Months as 'YYYY-MM' strings (strftime(ts, '%Y-%m')); weekdays as full names (dayname()); states as 2-letter codes.
- Count orders with COUNT(DISTINCT order_id) whenever order_items or payments are joined.
- Do not join payments and order_items together directly (row fan-out). Aggregate each per order first.
- Null delivery dates mean the order was not delivered; exclude them from delivery-time and late-rate math.
- Use NULLIF on denominators.
- Only read data. Never write, modify or delete.
- Data not in these tables (customer names, emails, phone numbers, marketing data, website traffic) is not available.
