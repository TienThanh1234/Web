# Tách app.py — hướng dẫn dùng

## Cấu trúc mới

```
flask-demo/
├── app.py                 # Entry ~25 dòng
├── config.py              # SECRET_KEY, path CSV, env
├── extensions.py          # Supabase client
├── utils.py               # read_csv, text_to_id, fetch_all_supabase...
├── routes/
│   ├── __init__.py        # register tất cả route
│   ├── auth.py
│   ├── characters.py
│   ├── skills.py
│   ├── supports.py
│   ├── items.py
│   ├── races.py
│   ├── titles.py
│   └── pages.py           # home, guides
├── services/
│   ├── auth_service.py
│   ├── character_service.py
│   ├── skill_service.py
│   ├── support_service.py
│   ├── item_service.py
│   ├── race_service.py
│   └── title_service.py
├── templates/             # giữ nguyên
├── static/                # giữ nguyên
├── Crawler/               # giữ nguyên
└── *.csv, .env            # giữ nguyên
```

## Cách cài

1. **Backup** `app.py` cũ (đổi tên thành `app_old.py`).
2. Copy toàn bộ file/folder trong gói này vào **root project** (cùng cấp với `templates/`).
3. Không đổi templates / static / csv / .env.
4. Chạy lại:

```bash
python app.py
```

## Lưu ý

- Endpoint `url_for("login")`, `url_for("characters")`… **giữ nguyên** như trước.
- Route `/titles` đã có (cần `titles.csv` nếu dùng trang Titles).
- Mỗi file route có `init_app(app)` — không dùng Blueprint name prefix để tránh vỡ link template.
