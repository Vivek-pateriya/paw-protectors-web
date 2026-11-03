BEGIN;
CREATE TABLE shop_categories (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text NOT NULL UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 100),
 active boolean NOT NULL DEFAULT true,
 version integer NOT NULL DEFAULT 1 CHECK(version>0)
);
CREATE TABLE shop_products (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 category_id bigint NOT NULL REFERENCES shop_categories(id),
 sku text NOT NULL UNIQUE CHECK(length(trim(sku)) BETWEEN 1 AND 60),
 name text NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 160),
 description text NOT NULL DEFAULT '' CHECK(length(description)<=5000),
 price_paise bigint NOT NULL CHECK(price_paise BETWEEN 1 AND 100000000),
 stock integer NOT NULL DEFAULT 0 CHECK(stock BETWEEN 0 AND 1000000),
 low_stock_threshold integer NOT NULL DEFAULT 5 CHECK(low_stock_threshold BETWEEN 0 AND 1000000),
 active boolean NOT NULL DEFAULT false,
 image_path text,
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX shop_product_browse ON shop_products(active,category_id,id DESC);
CREATE TABLE shop_carts (
 user_id bigint PRIMARY KEY REFERENCES users(id),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE shop_cart_items (
 user_id bigint NOT NULL REFERENCES shop_carts(user_id),
 product_id bigint NOT NULL REFERENCES shop_products(id),
 quantity integer NOT NULL CHECK(quantity BETWEEN 1 AND 99),
 PRIMARY KEY(user_id,product_id)
);
CREATE TABLE shop_orders (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES users(id),
 checkout_key uuid NOT NULL,
 request_hash text NOT NULL,
 cart_version integer NOT NULL,
 customer_name text NOT NULL CHECK(length(trim(customer_name)) BETWEEN 1 AND 120),
 phone text NOT NULL CHECK(length(trim(phone)) BETWEEN 5 AND 30),
 address text NOT NULL CHECK(length(trim(address)) BETWEEN 5 AND 500),
 city text NOT NULL CHECK(length(trim(city)) BETWEEN 1 AND 100),
 state text NOT NULL CHECK(length(trim(state)) BETWEEN 1 AND 100),
 postal_code text NOT NULL CHECK(postal_code ~ '^[0-9]{6}$'),
 status text NOT NULL DEFAULT 'placed' CHECK(status IN ('placed','confirmed','shipped','delivered','cancelled')),
 currency text NOT NULL DEFAULT 'INR' CHECK(currency='INR'),
 payment_method text NOT NULL DEFAULT 'cod' CHECK(payment_method='cod'),
 payment_status text NOT NULL DEFAULT 'pending' CHECK(payment_status IN ('pending','collected','cancelled')),
 subtotal_paise bigint NOT NULL CHECK(subtotal_paise>0),
 delivery_paise bigint NOT NULL DEFAULT 0 CHECK(delivery_paise=0),
 total_paise bigint NOT NULL CHECK(total_paise=subtotal_paise),
 tracking_reference text NOT NULL DEFAULT '' CHECK(length(tracking_reference)<=200),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,checkout_key),
 CHECK((status='delivered')=(payment_status='collected')),
 CHECK((status='cancelled')=(payment_status='cancelled'))
);
CREATE INDEX shop_order_owner ON shop_orders(user_id,id DESC);
CREATE INDEX shop_order_review ON shop_orders(status,id DESC);
CREATE TABLE shop_order_items (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 order_id bigint NOT NULL REFERENCES shop_orders(id),
 product_id bigint NOT NULL REFERENCES shop_products(id),
 sku text NOT NULL,
 name text NOT NULL,
 unit_price_paise bigint NOT NULL CHECK(unit_price_paise>0),
 quantity integer NOT NULL CHECK(quantity BETWEEN 1 AND 99),
 line_total_paise bigint NOT NULL CHECK(line_total_paise=unit_price_paise*quantity),
 UNIQUE(order_id,product_id)
);
CREATE TABLE shop_stock_movements (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 product_id bigint NOT NULL REFERENCES shop_products(id),
 order_id bigint REFERENCES shop_orders(id),
 actor_id bigint NOT NULL REFERENCES users(id),
 kind text NOT NULL CHECK(kind IN ('initial','adjustment','checkout','cancellation')),
 delta integer NOT NULL CHECK(delta<>0),
 resulting_stock integer NOT NULL CHECK(resulting_stock BETWEEN 0 AND 1000000),
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 1000),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK((kind IN ('checkout','cancellation'))=(order_id IS NOT NULL))
);
CREATE UNIQUE INDEX shop_stock_once ON shop_stock_movements(order_id,product_id,kind) WHERE order_id IS NOT NULL;
CREATE INDEX shop_stock_product ON shop_stock_movements(product_id,id DESC);
CREATE TABLE shop_order_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 order_id bigint NOT NULL REFERENCES shop_orders(id),
 actor_id bigint NOT NULL REFERENCES users(id),
 from_status text,
 to_status text NOT NULL,
 note text NOT NULL DEFAULT '' CHECK(length(note)<=1000),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER shop_categories_audit AFTER INSERT OR UPDATE ON shop_categories FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER shop_products_audit AFTER INSERT OR UPDATE ON shop_products FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER shop_orders_audit AFTER INSERT OR UPDATE ON shop_orders FOR EACH ROW EXECUTE FUNCTION audit_change();
ALTER TABLE reminders ADD COLUMN shop_order_id bigint REFERENCES shop_orders(id);
ALTER TABLE reminders DROP CONSTRAINT reminders_kind_check;
ALTER TABLE reminders ADD CONSTRAINT reminders_kind_check CHECK(kind IN ('vaccination','medication','appointment_reminder','appointment_booked','appointment_cancelled','appointment_completed','adoption_listing','adoption_application','shop_order'));
ALTER TABLE reminders DROP CONSTRAINT reminder_source;
ALTER TABLE reminders ADD CONSTRAINT reminder_source CHECK(
 (shop_order_id IS NULL AND (
  (kind='vaccination' AND vaccination_id IS NOT NULL AND medication_id IS NULL AND appointment_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL) OR
  (kind='medication' AND medication_id IS NOT NULL AND vaccination_id IS NULL AND appointment_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL) OR
  (kind LIKE 'appointment_%' AND appointment_id IS NOT NULL AND vaccination_id IS NULL AND medication_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL) OR
  (kind IN ('adoption_listing','adoption_application') AND adoption_listing_id IS NOT NULL AND vaccination_id IS NULL AND medication_id IS NULL AND appointment_id IS NULL))) OR
 (kind='shop_order' AND shop_order_id IS NOT NULL AND vaccination_id IS NULL AND medication_id IS NULL AND appointment_id IS NULL AND adoption_listing_id IS NULL AND adoption_application_id IS NULL)
);
INSERT INTO schema_versions(version) VALUES(6);
COMMIT;
