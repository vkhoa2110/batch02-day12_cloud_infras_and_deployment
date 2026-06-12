# Solution - Day 12 Cloud Infrastructure and Deployment

File này trả lời các câu hỏi chính từ Part 1 đến Part 5 trong `CODE_LAB.md`.

## Part 1 - Localhost vs Production

### Exercise 1.1 - Anti-patterns trong bản basic

Các vấn đề trong `01-localhost-vs-production/develop/app.py`:

1. Hardcode secret trong code: `OPENAI_API_KEY` và `DATABASE_URL` nằm trực tiếp trong source.
2. Log ra secret: code `print(f"[DEBUG] Using key: ...")` làm lộ API key trong logs.
3. Không có config management: `DEBUG`, `MAX_TOKENS`, host, port đều hardcode.
4. Bind `host="localhost"` nên chỉ dùng tốt trên máy local, không phù hợp container/cloud.
5. Port cố định `8000`, không đọc `PORT` từ environment như Railway/Render yêu cầu.
6. Bật `reload=True`, chỉ nên dùng khi dev, không nên dùng production.
7. Không có `/health` và `/ready`, platform không biết app sống hay sẵn sàng chưa.
8. Dùng `print()` thay vì structured logging nên khó search, parse, monitor.
9. Thiếu graceful shutdown, khi container bị stop có thể làm hỏng request đang xử lý.
10. Thiếu input validation và error handling rõ ràng.

### Exercise 1.2 - Basic version có production-ready không?

Basic app chạy được trên localhost, nhưng chưa production-ready. Nó phụ thuộc vào môi trường local, hardcode secret/port, không có health check, không có structured logs, không có graceful shutdown, và không đọc config từ environment variables.

### Exercise 1.3 - So sánh basic và advanced

| Feature | Basic | Advanced | Tại sao quan trọng? |
|---|---|---|---|
| Config | Hardcode trong code | Đọc từ environment qua `settings` | Dễ đổi giữa dev/staging/prod, không cần sửa code |
| Secrets | API key, DB URL nằm trong source | Lấy từ env var | Tránh lộ secret khi push GitHub |
| Host/Port | `localhost:8000` | `0.0.0.0` và `PORT` env | Chạy được trong container và cloud |
| Logging | `print()` | JSON structured logging | Dễ thu thập, search, monitor |
| Health check | Không có | Có `/health` | Platform biết khi nào restart app |
| Readiness | Không có | Có `/ready` | Load balancer biết khi nào route traffic |
| Shutdown | Không xử lý | Có lifespan và SIGTERM handler | Tắt app an toàn, giảm lỗi request |
| CORS | Không cấu hình | Cấu hình qua env | Kiểm soát frontend origin được phép gọi API |
| Validation | Ít kiểm tra input | Kiểm tra `question` | Trả lỗi rõ ràng, tránh request xấu |
| Metrics | Không có | Có `/metrics` | Hỗ trợ monitoring |

## Part 2 - Docker Containerization

### Exercise 2.1 - Dockerfile cơ bản

1. Base image là `python:3.11` trong `02-docker/develop/Dockerfile`.
2. Working directory là `/app`.
3. `COPY requirements.txt` trước để tận dụng Docker layer cache. Khi chỉ sửa code, Docker không cần cài lại dependencies.
4. `CMD` là command mặc định và có thể override khi `docker run`. `ENTRYPOINT` cố định hành vi chính của container hơn; arguments sau `docker run` thường được truyền vào ENTRYPOINT.

### Exercise 2.2 - Build và run

Lệnh build cần chạy từ project root:

```powershell
docker build -f 02-docker/develop/Dockerfile -t agent-develop .
docker run -p 8000:8000 agent-develop
curl.exe http://localhost:8000/health
```

Image size phụ thuộc môi trường build, nhưng bản `python:3.11` full thường lớn hơn bản `python:3.11-slim`. Kiểm tra bằng:

```powershell
docker images agent-develop
```

### Exercise 2.3 - Multi-stage build

Trong `02-docker/production/Dockerfile`:

- Stage 1 `builder`: dùng `python:3.11-slim`, cài build tools như `gcc`, `libpq-dev`, rồi cài Python dependencies vào `/root/.local`.
- Stage 2 `runtime`: dùng image runtime sạch, copy package đã cài từ builder, copy app code, tạo non-root user, expose port, khai báo healthcheck, chạy Uvicorn.

Image nhỏ và an toàn hơn vì runtime stage không chứa compiler, apt cache, build tools, và các file không cần thiết để chạy app.

### Exercise 2.4 - Docker Compose stack

Các service trong `02-docker/production/docker-compose.yml`:

- `nginx`: reverse proxy/load balancer, expose port `80` và `443`.
- `agent`: FastAPI app, chạy trong internal network.
- `redis`: cache/session/rate limit backend.
- `qdrant`: vector database cho RAG.

Architecture:

```text
Client
  |
  v
Nginx :80/:443
  |
  v
Agent :8000
  |----------------|
  v                v
Redis :6379     Qdrant :6333
```

Nginx nhận request từ client rồi proxy sang agent. Agent giao tiếp nội bộ với Redis và Qdrant qua Docker network `internal`.

## Part 3 - Cloud Deployment

### Exercise 3.1 - Railway

Railway deploy thành công khi:

- Service online.
- Có public URL.
- `/health` trả `200 OK`.
- `/ask` trả response JSON.

URL đã test trong lab:

```text
https://honest-playfulness-production-debd.up.railway.app
```

Test:

```powershell
curl.exe https://honest-playfulness-production-debd.up.railway.app/health
curl.exe --% -X POST https://honest-playfulness-production-debd.up.railway.app/ask -H "Content-Type: application/json" -d "{\"question\":\"What is deployment?\"}"
```

### Exercise 3.2 - So sánh `render.yaml` và `railway.toml`

| Tiêu chí | `railway.toml` | `render.yaml` |
|---|---|---|
| Mục đích | Config build/deploy cho Railway service | Blueprint khai báo hạ tầng Render |
| Build | `builder = "NIXPACKS"` hoặc Dockerfile | `buildCommand`, `runtime`, Docker hoặc Python |
| Start command | `startCommand` trong `[deploy]` | `startCommand` trong từng service |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Env vars | Đặt qua Railway Dashboard/CLI | Khai báo trong `envVars`, secret có thể `sync: false` |
| Nhiều service | Ít khai báo trực tiếp trong file này | Có thể khai báo web service, Redis, disk... |
| Auto deploy | Qua GitHub integration của Railway | `autoDeploy: true` |
| Region/plan | Thường set trong dashboard | Khai báo được trong YAML |

Kết luận: Railway config ngắn gọn cho một service. Render YAML giống Infrastructure as Code hơn vì khai báo được nhiều resource trong cùng file.

### Exercise 3.3 - Cloud Run CI/CD

`cloudbuild.yaml` mô tả pipeline:

1. Test: cài requirements và chạy pytest.
2. Build: build Docker image, tag bằng `$COMMIT_SHA` và `latest`.
3. Push: push image lên `gcr.io/$PROJECT_ID/ai-agent`.
4. Deploy: deploy image lên Cloud Run với region `asia-southeast1`, public endpoint, min/max instances, memory/cpu, env vars và secrets.

`service.yaml` mô tả Cloud Run service:

- Tên service: `ai-agent`.
- Public ingress.
- Autoscaling `minScale=1`, `maxScale=10`.
- `containerConcurrency=80`.
- Resource limits CPU/memory.
- Env vars và Secret Manager references.
- Liveness/startup probes.

## Part 4 - API Security

### Exercise 4.1 - API Key authentication

API key được check trong `04-api-gateway/develop/app.py`, hàm `verify_api_key()`:

```python
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
```

Luồng xử lý:

- Không gửi `X-API-Key` -> `401 Unauthorized`.
- Gửi sai key -> `403 Forbidden`.
- Gửi đúng key -> request vào được `/ask`.

Key hợp lệ được server đọc từ environment variable:

```powershell
$env:AGENT_API_KEY="secret-key-123"
```

Rotate key bằng cách đổi `AGENT_API_KEY` trên server/cloud platform rồi restart/redeploy service. Production tốt hơn có thể hỗ trợ 2 key tạm thời trong thời gian chuyển đổi để tránh downtime.

### Exercise 4.2 - JWT authentication

JWT flow trong `04-api-gateway/production/auth.py`:

1. Client gọi `POST /auth/token` với username/password.
2. `authenticate_user()` kiểm tra credentials trong `DEMO_USERS`.
3. `create_token()` tạo JWT chứa `sub`, `role`, `iat`, `exp`, ký bằng `HS256`.
4. Client gửi token trong header:

```text
Authorization: Bearer <token>
```

5. `verify_token()` decode token, kiểm tra chữ ký và expiry.
6. Token thiếu -> `401`, token sai/invalid -> `403`, token hết hạn -> `401`.

Demo users:

```text
student / demo123  -> role user
teacher / teach456 -> role admin
```

### Exercise 4.3 - Rate limiting

Algorithm trong `rate_limiter.py` là **Sliding Window Counter** dùng `deque` timestamps.

Cách hoạt động:

1. Mỗi user có một deque lưu thời điểm request.
2. Mỗi request mới sẽ xóa timestamp cũ ngoài window 60 giây.
3. Nếu số timestamp còn lại >= limit thì trả `429 Too Many Requests`.
4. Nếu chưa vượt limit thì append timestamp hiện tại.

Limit:

- User thường: `10 requests / 60 giây`.
- Admin: `100 requests / 60 giây`.

Admin không bypass hoàn toàn, nhưng được quota cao hơn nhờ code chọn `rate_limiter_admin` khi `role == "admin"`. Nếu muốn bypass thật, có thể bỏ qua `limiter.check()` cho admin, nhưng cách hiện tại an toàn hơn vì vẫn có giới hạn.

Khi hit limit, response có status `429` và headers như:

```text
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
Retry-After
```

### Exercise 4.4 - Cost guard

`cost_guard.py` bảo vệ chi phí LLM bằng cách:

- Đếm input/output tokens theo user.
- Tính cost dựa trên giá token.
- Có budget theo user và global budget.
- Cảnh báo khi dùng >= 80%.
- Chặn user bằng `402 Payment Required` nếu vượt user budget.
- Chặn toàn hệ thống bằng `503` nếu vượt global budget.

Trong code hiện tại:

```text
daily_budget_usd = 1.0 per user
global_daily_budget_usd = 10.0
```

Luồng đúng:

```text
check_budget(username) -> gọi trước LLM
record_usage(username, input_tokens, output_tokens) -> gọi sau LLM
get_usage(username) -> xem usage hiện tại
```

Nếu làm production thật, usage nên lưu trong Redis/DB thay vì memory. Key Redis có thể theo tháng:

```python
key = f"budget:{user_id}:{YYYY_MM}"
```

Sau đó dùng `INCRBYFLOAT` để cộng cost và `EXPIRE` để tự reset sau chu kỳ billing.

## Part 5 - Scaling and Reliability

### Exercise 5.1 - Health checks

`/health` là liveness probe: trả lời câu hỏi "process còn sống không?". Nếu endpoint fail, platform có thể restart container.

`/ready` là readiness probe: trả lời câu hỏi "instance đã sẵn sàng nhận traffic chưa?". Nếu chưa ready, load balancer không nên route traffic vào instance đó.

Trong `05-scaling-reliability/develop/app.py`:

- `/health` trả uptime, version, environment, checks.
- `/ready` trả `503` nếu `_is_ready == False`, ngược lại trả `{"ready": true}`.

### Exercise 5.2 - Graceful shutdown

Graceful shutdown nghĩa là khi platform gửi `SIGTERM`, app:

1. Ngừng nhận request mới hoặc đánh dấu không ready.
2. Chờ request đang xử lý hoàn thành.
3. Đóng connection/resource.
4. Thoát an toàn.

Trong bản develop, app dùng lifespan của FastAPI và `_in_flight_requests` để chờ request đang xử lý. Signal handler log lại `SIGTERM`/`SIGINT`, còn Uvicorn xử lý shutdown.

### Exercise 5.3 - Stateless design

Anti-pattern:

```python
conversation_history = {}
```

Vấn đề: khi scale nhiều instance, mỗi instance có RAM riêng. User request lần 1 có thể vào instance A, lần 2 vào instance B, nên B không thấy history trong RAM của A.

Correct design: lưu state vào Redis:

```text
Agent instance A ----|
Agent instance B ----|--> Redis session/history
Agent instance C ----|
```

Trong `05-scaling-reliability/production/app.py`, session/history được lưu qua key như `session:{session_id}`. Khi Redis có sẵn, bất kỳ instance nào cũng đọc được cùng conversation history.

### Exercise 5.4 - Load balancing

Stack production chạy:

```text
Client -> Nginx -> agent replicas -> Redis
```

Chạy:

```powershell
cd 05-scaling-reliability/production
docker compose up --scale agent=3
```

Quan sát mong đợi:

- Có 3 agent containers.
- Nginx nhận request từ client.
- Docker DNS/Nginx phân phối request sang nhiều agent.
- Response có `served_by` khác nhau qua các lần gọi.
- Nếu một instance die, request vẫn có thể đi sang instance khác.

### Exercise 5.5 - Test stateless

`test_stateless.py` kiểm tra:

1. Tạo conversation/session.
2. Gửi nhiều request qua load balancer.
3. Kill hoặc thay đổi instance.
4. Gọi tiếp và kiểm tra history còn tồn tại.

Nếu Redis hoạt động, conversation vẫn còn dù request sau được phục vụ bởi instance khác. Nếu dùng in-memory store, test này có thể fail hoặc history bị mất khi request đổi instance.

## Tổng kết checkpoint

### Checkpoint 1

- Hiểu vì sao localhost code chưa production-ready.
- Biết dùng env vars, health check, structured logs, graceful shutdown.

### Checkpoint 2

- Build/run Docker image.
- Hiểu layer cache, multi-stage build, Docker Compose stack.
- Biết debug container bằng logs và healthcheck.

### Checkpoint 3

- Deploy được ít nhất một platform.
- Có public URL hoạt động.
- Biết set env vars và xem logs trên cloud.

### Checkpoint 4

- API key auth hoạt động.
- JWT flow hoạt động.
- Rate limit trả `429` khi vượt quota.
- Cost guard theo dõi và chặn khi vượt budget.

### Checkpoint 5

- Có `/health` và `/ready`.
- Có graceful shutdown.
- State chuyển ra Redis thay vì memory.
- Nginx load balance được nhiều agent instances.
- Stateless test vẫn giữ conversation khi instance thay đổi.
