# Deploy [`SRS Vocabulary`](srs_fastapi.py)

## 1. Cách khuyến nghị: Docker

Repository đã được đóng gói sẵn bằng [`Dockerfile`](Dockerfile) và [`compose.yaml`](compose.yaml).

### Chạy local/VPS

```bash
docker compose up -d --build
```

Sau khi chạy xong, ứng dụng sẽ mở tại:

```text
http://<IP-hoặc-domain>:8000
```

### Đổi cổng public

```bash
APP_PORT=8080 docker compose up -d --build
```

Khi đó ứng dụng sẽ ở:

```text
http://<IP-hoặc-domain>:8080
```

## 2. Dữ liệu cần được lưu bền

Ứng dụng lưu tiến độ học trong thư mục [`logs`](logs) và đọc bộ từ trong thư mục [`vocab_sets`](vocab_sets).

Trong [`compose.yaml`](compose.yaml), hai thư mục này đã được mount sẵn:

- [`./logs`](logs) -> `/app/logs`
- [`./vocab_sets`](vocab_sets) -> `/app/vocab_sets`

Vì vậy khi restart container, tiến độ học vẫn còn.

## 3. Deploy lên nền tảng khác

Nếu deploy lên Render, Railway, Fly.io hoặc VPS tự cấu hình:

- Build từ [`Dockerfile`](Dockerfile)
- Mở cổng theo biến môi trường `PORT`
- Mount persistent storage cho thư mục `/app/logs`
- Nếu muốn thay bộ từ mà không rebuild image, mount thêm `/app/vocab_sets`

## 4. Chạy không dùng Docker

### Cài dependency

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Chạy app

```bash
PORT=8000 HOST=0.0.0.0 python3 srs_fastapi.py
```

## 5. Reverse proxy domain thật

Nếu dùng Nginx/Caddy phía trước:

- proxy về `127.0.0.1:8000`
- bật HTTPS
- giữ nguyên path `/` và `/api/*`

## 6. File chính liên quan deploy

- Backend: [`srs_fastapi.py`](srs_fastapi.py)
- Lõi học: [`terminal_srs.py`](terminal_srs.py)
- Frontend chính: [`srs_study_v2.html`](srs_study_v2.html)
- Dependency: [`requirements.txt`](requirements.txt)
- Image build: [`Dockerfile`](Dockerfile)
- Chạy nhanh: [`compose.yaml`](compose.yaml)
