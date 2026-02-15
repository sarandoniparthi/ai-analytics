DROP VIEW IF EXISTS v_payment_scoped;
CREATE OR REPLACE VIEW v_payment_scoped AS
SELECT
  p.payment_id,
  c.store_id,
  p.customer_id,
  p.staff_id,
  p.rental_id,
  p.amount,
  p.payment_date
FROM payment p
JOIN customer c ON c.customer_id = p.customer_id;

DROP VIEW IF EXISTS v_customer_masked;
CREATE OR REPLACE VIEW v_customer_masked AS
SELECT
  customer_id,
  store_id,
  LEFT(first_name, 1) || '***' AS first_name_masked,
  LEFT(last_name, 1) || '***' AS last_name_masked,
  activebool
FROM customer;

DROP VIEW IF EXISTS v_rental_scoped;
CREATE OR REPLACE VIEW v_rental_scoped AS
SELECT
  r.rental_id,
  c.store_id,
  r.rental_date,
  r.inventory_id,
  r.customer_id,
  r.return_date,
  r.staff_id,
  r.last_update
FROM rental r
JOIN customer c ON c.customer_id = r.customer_id;
