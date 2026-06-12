# Food chatbot tool

Full flow cho demo ShopeeFood:

1. GPT-4o mini parse câu hỏi thành task JSON.
2. Tool query SQLite mock data trong `codebase/mock_data/shopee_food_db_hcm_q1`.
3. GPT-4o mini nhận task JSON + món tìm được và viết câu trả lời cuối cùng.

## Chạy full API flow

```powershell
$env:OPENAI_API_KEY="sk-..."
python -X utf8 -m codebase.food_chatbot "Gợi ý món dưới 50k giao nhanh"
```

## Chạy offline để demo logic query

```powershell
python -X utf8 -m codebase.food_chatbot --parse-mode rules --answer-mode template "Gợi ý món dưới 50k giao nhanh"
```

## Dùng task JSON đã có sẵn

```powershell
python -X utf8 -m codebase.food_chatbot --task-json task.json --answer-mode template --show-json
```

`--show-json` in ra cả task, SQL query, params và các item lấy từ mock data để debug.
