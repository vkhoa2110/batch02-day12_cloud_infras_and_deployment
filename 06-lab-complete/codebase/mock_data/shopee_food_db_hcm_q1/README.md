# ShopeeFood-style Mock Database - HCM Quận 1

Bộ dữ liệu mock theo kiểu cơ sở dữ liệu quan hệ, chỉ cho một vùng: **Quận 1, TP. Hồ Chí Minh**.

## Thống kê

- Region: 1
- Wards/phường: 8
- Shops: 44
- Shop addresses: 44
- Menu items: 264
- Reviews: 353
- Promotions: 8
- Recommendation view rows: 264

## File chính

- `shopee_food_mock_hcm_q1.sqlite`: SQLite database dùng ngay.
- `shopee_food_schema.sql`: chỉ schema.
- `shopee_food_seed.sql`: schema + toàn bộ dữ liệu seed.
- Folder CSV trong zip: mỗi bảng một file CSV.

## Bảng quan trọng

- `regions`, `wards`: vùng giao hàng và phường.
- `shops`: thông tin shop/quán, rating, trạng thái, thời gian chuẩn bị/giao.
- `shop_addresses`: địa chỉ đầy đủ, lat/lng, landmark, bán kính giao hàng.
- `shop_opening_hours`: giờ mở cửa theo từng ngày.
- `cuisines`, `shop_cuisines`: loại ẩm thực của shop.
- `tags`, `shop_tags`, `item_tags`: tag phục vụ lọc/gợi ý chatbot.
- `menu_categories`, `menu_items`: danh mục menu và món ăn.
- `ingredients`, `item_ingredients`, `allergens`, `item_allergens`: nguyên liệu và dị ứng.
- `item_options`, `item_toppings`: option món và topping.
- `promotions`, `shop_promotions`, `item_promotions`: khuyến mãi.
- `delivery_fee_rules`: phí giao hàng mock theo shop.
- `reviews`, `customers`: review mẫu.
- `chatbot_intents`: intent mẫu cho chatbot.
- `v_recommendation_items`: view gộp sẵn để truy vấn gợi ý món.

## Query mẫu

```sql
-- Gợi ý món dưới 50k, shop đang mở
SELECT item_name, effective_price, shop_name, avg_delivery_time_min, full_address, recommendation_score
FROM v_recommendation_items
WHERE effective_price <= 50000
  AND is_available = 1
  AND shop_status = 'open'
ORDER BY recommendation_score DESC
LIMIT 10;
```

```sql
-- Gợi ý món cay cấp 3 trở lên
SELECT item_name, spicy_level, effective_price, shop_name, shop_rating
FROM v_recommendation_items
WHERE spicy_level >= 3
  AND is_available = 1
ORDER BY recommendation_score DESC
LIMIT 10;
```

```sql
-- Lấy shop kèm địa chỉ
SELECT s.id, s.name, s.status, s.rating_avg, a.full_address, a.latitude, a.longitude
FROM shops s
JOIN shop_addresses a ON s.id = a.shop_id
ORDER BY s.rating_avg DESC;
```
