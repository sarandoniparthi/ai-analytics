WITH v AS (
  SELECT ('[' || array_to_string(array_fill(0.0::float8, ARRAY[1536]), ',') || ']')::vector AS embedding
),
seed_docs(doc_type, source, content) AS (
  VALUES
    ('schema', 'pagila.payment', 'payment contains payment_id, customer_id, staff_id, rental_id, amount, payment_date.'),
    ('schema', 'pagila.rental', 'rental contains rental_id, rental_date, inventory_id, customer_id, return_date, staff_id.'),
    ('schema', 'pagila.customer', 'customer contains customer_id, store_id, first_name, last_name, email, active.'),
    ('schema', 'pagila.inventory', 'inventory links films to stores using inventory_id, film_id, store_id.'),
    ('schema', 'v_payment_scoped', 'v_payment_scoped is the approved analytics view for payment metrics by store and customer.'),
    ('schema', 'v_customer_masked', 'v_customer_masked provides customer fields with masked email for safe marketing analysis.'),
    ('schema', 'v_rental_scoped', 'v_rental_scoped is the approved analytics view for rentals and customer activity.'),
    ('metric_glossary', 'revenue', 'Revenue means SUM(amount) from v_payment_scoped for the selected scope and time window.'),
    ('metric_glossary', 'rentals', 'Rental count means COUNT(*) from v_rental_scoped under role/store restrictions.'),
    ('metric_glossary', 'active_customers', 'Active customers means COUNT(DISTINCT customer_id) in scoped views.'),
    ('widget_policy', 'widget_policy_trend', 'If the user asks for trend, over time, daily, monthly, or time series, prefer line chart.'),
    ('widget_policy', 'widget_policy_ranking', 'If the user asks for top, rank, leaderboard, or compare categories, prefer bar chart.'),
    ('widget_policy', 'widget_policy_distribution', 'If the user asks for share, split, proportion, or distribution, prefer pie chart.'),
    ('widget_policy', 'widget_policy_kpi', 'If the result is a single aggregate metric like total/count/average, show metric_card first.'),
    ('governance', 'sql_safety', 'Only SELECT or WITH SELECT queries are allowed. DDL and DML are blocked.'),
    ('governance', 'views_policy', 'Queries must reference only allowed_views resolved from role policy.'),
    ('governance', 'result_limit', 'Query responses must include LIMIT and default to LIMIT 200 when missing.'),
    ('governance', 'pii_policy', 'Marketing role should use v_customer_masked and avoid raw PII exposure.'),
    ('governance', 'security_scope', 'All answers must return security info: role, store_id, allowed_views, rls=true.')
)
INSERT INTO rag_documents (doc_type, source, content, embedding)
SELECT s.doc_type, s.source, s.content, v.embedding
FROM seed_docs s
CROSS JOIN v
WHERE NOT EXISTS (
  SELECT 1 FROM rag_documents r WHERE r.doc_type = s.doc_type AND r.source = s.source
);
