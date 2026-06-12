PRAGMA foreign_keys = ON;

CREATE TABLE regions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  country TEXT NOT NULL,
  currency TEXT NOT NULL,
  timezone TEXT NOT NULL,
  center_lat REAL NOT NULL,
  center_lng REAL NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE wards (
  id TEXT PRIMARY KEY,
  region_id TEXT NOT NULL,
  name TEXT NOT NULL,
  center_lat REAL NOT NULL,
  center_lng REAL NOT NULL,
  FOREIGN KEY (region_id) REFERENCES regions(id)
);

CREATE TABLE shops (
  id TEXT PRIMARY KEY,
  region_id TEXT NOT NULL,
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  description TEXT,
  phone TEXT,
  email TEXT,
  avatar_url TEXT,
  cover_url TEXT,
  business_type TEXT NOT NULL,
  price_level INTEGER NOT NULL CHECK (price_level BETWEEN 1 AND 4),
  rating_avg REAL NOT NULL CHECK (rating_avg BETWEEN 0 AND 5),
  rating_count INTEGER NOT NULL DEFAULT 0,
  sold_count INTEGER NOT NULL DEFAULT 0,
  favorite_count INTEGER NOT NULL DEFAULT 0,
  min_order_amount INTEGER NOT NULL DEFAULT 0,
  avg_prepare_time_min INTEGER NOT NULL DEFAULT 10,
  avg_delivery_time_min INTEGER NOT NULL DEFAULT 20,
  status TEXT NOT NULL CHECK (status IN ('open','closed','busy','temporarily_closed')),
  is_verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (region_id) REFERENCES regions(id)
);

CREATE TABLE shop_addresses (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL UNIQUE,
  ward_id TEXT NOT NULL,
  street_address TEXT NOT NULL,
  full_address TEXT NOT NULL,
  landmark TEXT,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  geohash TEXT,
  delivery_radius_km REAL NOT NULL DEFAULT 5,
  parking_available INTEGER NOT NULL DEFAULT 0,
  dine_in_available INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (ward_id) REFERENCES wards(id)
);

CREATE TABLE shop_opening_hours (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
  open_time TEXT,
  close_time TEXT,
  is_closed INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  UNIQUE (shop_id, day_of_week)
);

CREATE TABLE cuisines (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  parent_name TEXT
);

CREATE TABLE shop_cuisines (
  shop_id TEXT NOT NULL,
  cuisine_id TEXT NOT NULL,
  PRIMARY KEY (shop_id, cuisine_id),
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (cuisine_id) REFERENCES cuisines(id)
);

CREATE TABLE tags (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  tag_type TEXT NOT NULL CHECK (tag_type IN ('shop','item','diet','occasion','taste','system'))
);

CREATE TABLE shop_tags (
  shop_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  PRIMARY KEY (shop_id, tag_id),
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id)
);

CREATE TABLE menu_categories (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  name TEXT NOT NULL,
  display_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  UNIQUE (shop_id, name)
);

CREATE TABLE menu_items (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  base_price INTEGER NOT NULL CHECK (base_price >= 0),
  sale_price INTEGER,
  image_url TEXT,
  rating_avg REAL NOT NULL DEFAULT 0,
  rating_count INTEGER NOT NULL DEFAULT 0,
  sold_count INTEGER NOT NULL DEFAULT 0,
  prepare_time_min INTEGER NOT NULL DEFAULT 10,
  spicy_level INTEGER NOT NULL DEFAULT 0 CHECK (spicy_level BETWEEN 0 AND 5),
  calories_estimate INTEGER,
  portion_size TEXT,
  is_available INTEGER NOT NULL DEFAULT 1,
  is_signature INTEGER NOT NULL DEFAULT 0,
  is_combo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES menu_categories(id) ON DELETE CASCADE
);

CREATE TABLE item_tags (
  item_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  PRIMARY KEY (item_id, tag_id),
  FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id)
);

CREATE TABLE ingredients (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  ingredient_type TEXT
);

CREATE TABLE item_ingredients (
  item_id TEXT NOT NULL,
  ingredient_id TEXT NOT NULL,
  is_main INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (item_id, ingredient_id),
  FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE CASCADE,
  FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
);

CREATE TABLE allergens (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE item_allergens (
  item_id TEXT NOT NULL,
  allergen_id TEXT NOT NULL,
  PRIMARY KEY (item_id, allergen_id),
  FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE CASCADE,
  FOREIGN KEY (allergen_id) REFERENCES allergens(id)
);

CREATE TABLE item_options (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  option_group TEXT NOT NULL,
  option_name TEXT NOT NULL,
  price_delta INTEGER NOT NULL DEFAULT 0,
  is_default INTEGER NOT NULL DEFAULT 0,
  display_order INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE CASCADE
);

CREATE TABLE item_toppings (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  name TEXT NOT NULL,
  price INTEGER NOT NULL DEFAULT 0,
  is_available INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
);

CREATE TABLE promotions (
  id TEXT PRIMARY KEY,
  code TEXT UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  promo_type TEXT NOT NULL CHECK (promo_type IN ('percent','amount','free_delivery','combo','buy_x_get_y')),
  value INTEGER NOT NULL DEFAULT 0,
  min_order_amount INTEGER NOT NULL DEFAULT 0,
  max_discount_amount INTEGER,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE shop_promotions (
  shop_id TEXT NOT NULL,
  promotion_id TEXT NOT NULL,
  PRIMARY KEY (shop_id, promotion_id),
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (promotion_id) REFERENCES promotions(id) ON DELETE CASCADE
);

CREATE TABLE item_promotions (
  item_id TEXT NOT NULL,
  promotion_id TEXT NOT NULL,
  PRIMARY KEY (item_id, promotion_id),
  FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE CASCADE,
  FOREIGN KEY (promotion_id) REFERENCES promotions(id) ON DELETE CASCADE
);

CREATE TABLE delivery_fee_rules (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  base_fee INTEGER NOT NULL,
  fee_per_km INTEGER NOT NULL,
  free_delivery_min_order INTEGER,
  max_distance_km REAL NOT NULL DEFAULT 6,
  estimated_distance_km REAL NOT NULL,
  estimated_fee INTEGER NOT NULL,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
);

CREATE TABLE payment_methods (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE shop_payment_methods (
  shop_id TEXT NOT NULL,
  payment_method_id TEXT NOT NULL,
  PRIMARY KEY (shop_id, payment_method_id),
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id)
);

CREATE TABLE customers (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  phone TEXT,
  default_lat REAL,
  default_lng REAL,
  dietary_preference TEXT,
  allergen_note TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE reviews (
  id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  item_id TEXT,
  customer_id TEXT NOT NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment TEXT,
  sentiment TEXT CHECK (sentiment IN ('positive','neutral','negative')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES menu_items(id) ON DELETE SET NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE chatbot_intents (
  id TEXT PRIMARY KEY,
  intent_name TEXT NOT NULL UNIQUE,
  sample_user_message TEXT NOT NULL,
  filter_json TEXT NOT NULL,
  ranking_json TEXT NOT NULL
);

CREATE VIEW v_recommendation_items AS
SELECT
  mi.id AS item_id,
  mi.name AS item_name,
  mi.base_price,
  COALESCE(mi.sale_price, mi.base_price) AS effective_price,
  mi.rating_avg AS item_rating,
  mi.sold_count AS item_sold_count,
  mi.spicy_level,
  mi.calories_estimate,
  mi.is_available,
  mi.is_signature,
  mc.name AS category_name,
  s.id AS shop_id,
  s.name AS shop_name,
  s.rating_avg AS shop_rating,
  s.status AS shop_status,
  s.avg_delivery_time_min,
  s.min_order_amount,
  sa.full_address,
  sa.latitude,
  sa.longitude,
  dfr.estimated_fee AS estimated_delivery_fee,
  ROUND(
    (mi.rating_avg / 5.0) * 0.35 +
    MIN(mi.sold_count / 1800.0, 1.0) * 0.25 +
    (1.0 - MIN(s.avg_delivery_time_min / 45.0, 1.0)) * 0.20 +
    CASE WHEN mi.sale_price IS NOT NULL AND mi.sale_price < mi.base_price THEN 0.10 ELSE 0 END +
    CASE WHEN mi.is_available = 1 AND s.status = 'open' THEN 0.10 ELSE -0.10 END,
    4
  ) AS recommendation_score
FROM menu_items mi
JOIN shops s ON mi.shop_id = s.id
JOIN shop_addresses sa ON s.id = sa.shop_id
JOIN menu_categories mc ON mi.category_id = mc.id
LEFT JOIN delivery_fee_rules dfr ON s.id = dfr.shop_id;

CREATE INDEX idx_shops_region_status ON shops(region_id, status);
CREATE INDEX idx_shop_addresses_ward ON shop_addresses(ward_id);
CREATE INDEX idx_menu_items_shop_available ON menu_items(shop_id, is_available);
CREATE INDEX idx_menu_items_price ON menu_items(base_price, sale_price);
CREATE INDEX idx_menu_items_spicy ON menu_items(spicy_level);
CREATE INDEX idx_item_tags_tag ON item_tags(tag_id);
CREATE INDEX idx_reviews_shop ON reviews(shop_id);
CREATE INDEX idx_via_delivery_shop ON delivery_fee_rules(shop_id);
