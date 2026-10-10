"""
Web quản lý nhỏ để kiểm soát script: bài nào đã được bình luận, bình luận gì, lúc mấy giờ, có bị chặn/từ chối không.

Chạy:  python web.py   rồi mở http://127.0.0.1:5000
"""
import io
import os
import re
from datetime import datetime, timedelta

import psutil

from flask import Flask, jsonify, request, send_from_directory, send_file

from config import Config
from modules.db import Database, SENT, PENDING, BLOCKED, ERROR, REJECTED, REJECTED_DELETED
from modules import products as prod
from modules import group_lists as gl
from modules.group_checker import usable_groups
from modules.group_finder import is_hanoi_group
from modules import filters as flt

WEB_DIR = os.path.join(Config.BASE_DIR, "web")
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # ảnh / file Excel tải lên tối đa 25MB
db = Database(Config.DB_FILE)
prod.ensure_seed(db, Config)
prod.ensure_variants(db)
gl.ensure_builtin(db, Config)

PROBLEM_COMMENT = (PENDING, BLOCKED, ERROR, REJECTED, REJECTED_DELETED)


def is_problem(post, comments):
    return (post["status"] in ("Một phần", "Thất bại")
            or any(c["status"] in PROBLEM_COMMENT for c in comments)
            or (post["verify_result"] or "").startswith(("Không thấy", "Chỉ còn")))


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/summary")
def summary():
    day = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    like = day + "%"
    posts = db.query("SELECT status, verify_result FROM posts WHERE found_at LIKE ?", (like,))
    comments = db.query("SELECT status FROM comments WHERE sent_at LIKE ?", (like,))
    count = lambda rows, key, *vals: sum(r[key] in vals for r in rows)

    last = db.query("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    last = last[0] if last else None
    script = {"state": "unknown", "text": "Chưa có lượt quét nào"}
    if last:
        started = datetime.strptime(last["started_at"], "%Y-%m-%d %H:%M:%S")
        if not last["finished_at"] and datetime.now() - started < timedelta(hours=6):
            script = {"state": "running", "text": f"Đang chạy vòng quét & bình luận (bắt đầu {started:%H:%M})"}
        elif last["finished_at"]:
            finished = datetime.strptime(last["finished_at"], "%Y-%m-%d %H:%M:%S")
            nxt = finished + timedelta(minutes=Config.ROUND_IDLE_MINUTES)
            if datetime.now() - finished > timedelta(minutes=Config.ROUND_IDLE_MINUTES * 3 + 30):
                script = {"state": "stale", "text": f"Vòng cuối xong {finished:%H:%M %d/%m} — script có thể đã dừng"}
            else:
                script = {"state": "idle", "text": f"Vòng cuối xong {finished:%H:%M}, vòng kế chậm nhất {nxt:%H:%M}"}

    blocked_until = db.get_setting("blocked_until")
    if blocked_until and datetime.strptime(blocked_until, "%Y-%m-%d %H:%M:%S") < datetime.now():
        blocked_until = None

    return jsonify({
        "date": day,
        "posts_commented": count(posts, "status", "Hoàn tất", "Một phần"),
        "posts_skipped": sum((p["status"] or "").startswith("Bỏ qua") for p in posts),
        "daily_limit": Config.MAX_COMMENTED_POSTS_PER_DAY,
        "comments_sent": count(comments, "status", SENT),
        "comments_pending": count(comments, "status", PENDING),
        "comments_blocked": count(comments, "status", BLOCKED),
        "comments_error": count(comments, "status", ERROR),
        "comments_rejected": count(comments, "status", REJECTED, REJECTED_DELETED),
        "comments_rejected_left": count(comments, "status", REJECTED),
        "removed": sum((p["verify_result"] or "").startswith(("Không thấy", "Chỉ còn")) for p in posts),
        "paused": db.is_paused(),
        "blocked_until": blocked_until,
        "script": script,
        "max_age": Config.MAX_POST_AGE_MINUTES,
        "joins_today": db.joins_today(),
        "join_limit": Config.JOIN_PER_DAY,
    })


@app.get("/api/posts")
def posts():
    day = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    status = request.args.get("status", "all")
    rows = db.query("SELECT * FROM posts WHERE found_at LIKE ? ORDER BY found_at DESC", (day + "%",))
    by_post = {}
    if rows:
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        for c in db.query(f"SELECT * FROM comments WHERE post_id IN ({marks}) ORDER BY idx", ids):
            by_post.setdefault(c["post_id"], []).append(c)

    result = []
    for r in rows:
        cs = by_post.get(r["id"], [])
        r["comments"] = cs
        r["problem"] = is_problem(r, cs)
        if status == "problem" and not r["problem"]:
            continue
        if status == "ok" and (r["problem"] or r["status"] != "Hoàn tất"):
            continue
        if status == "skip" and not (r["status"] or "").startswith("Bỏ qua"):
            continue
        result.append(r)
    return jsonify(result)


@app.get("/api/runs")
def runs():
    return jsonify(db.query("SELECT * FROM runs ORDER BY id DESC LIMIT 15"))


@app.get("/api/joins")
def joins():
    return jsonify(db.query("SELECT * FROM group_join ORDER BY checked_at DESC"))


@app.get("/api/decisions")
def decisions():
    """Quyết định bình luận / bỏ qua từng bài (kèm ý định MUA/BÁN, điểm tương tác, lý do) — tab Phân loại bài"""
    day = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    limit = request.args.get("limit", "300")
    rows = db.decisions(request.args.get("intent") or None, request.args.get("decision") or None, day,
                        limit=min(int(limit), 2000) if limit.isdigit() else 300)
    return jsonify({
        "rows": rows,
        "counts": db.decision_counts(day),
        "settings": {"intent_filter": Config.INTENT_FILTER, "min_engagement": Config.POST_MIN_ENGAGEMENT,
                     "ai": bool(Config.INTENT_AI and Config.GEMINI_API_KEY), "ai_calls_today": db.ai_calls_today(),
                     "ai_limit": Config.GEMINI_MAX_CALLS_PER_DAY,
                     "weights": Config.ENGAGEMENT_WEIGHTS, "min_members": Config.GROUP_MIN_MEMBERS,
                     "min_members_hanoi": Config.GROUP_MIN_MEMBERS_HANOI,
                     "min_posts_per_day": Config.GROUP_MIN_POSTS_PER_DAY,
                     "cache_hours": Config.GROUP_STATS_CACHE_HOURS},
    })


@app.get("/api/groupstats")
def group_stats():
    """Số thành viên / bài mỗi ngày của các nhóm (đọc ở trang Giới thiệu) và nhóm nào đủ điều kiện quét"""
    rows = []
    regions = {g["group_url"]: g.get("region", "") for g in gl.load_groups(db, Config, enabled_only=False)}
    for s in db.all_group_stats():
        hanoi = is_hanoi_group({**s, "region": regions.get(s["group_url"], "")})  # nhóm Hà Nội cần ít thành viên hơn
        v = flt.run_filters(flt.GROUP_FILTERS, {**s, "hanoi": hanoi}, Config)
        rows.append({**s, "ok": v.ok, "reason": v.reason})
    return jsonify({"rows": rows, "refresh_pending": db.get_setting("group_stats_refresh") == "1"})


@app.post("/api/groupstats/refresh")
def group_stats_refresh():
    """Yêu cầu bot đọc lại số thành viên mọi nhóm ở vòng quét tới (bỏ qua cache 24 giờ)"""
    db.set_setting("group_stats_refresh", "1")
    return jsonify({"ok": True})


@app.post("/api/pause")
def pause():
    paused = bool(request.get_json(force=True).get("paused"))
    db.set_setting("paused", "1" if paused else "0")
    return jsonify({"paused": paused})


@app.post("/api/unblock")
def unblock():
    db.set_setting("blocked_until", "")
    return jsonify({"ok": True})


@app.get("/api/safe")
def safe_groups():
    return jsonify({
        "all": db.get_setting("safe_all", "0") == "1",
        "all_reason": db.get_setting("safe_all_reason", ""),
        "groups": db.query("SELECT * FROM safe_groups ORDER BY since DESC"),
    })


@app.post("/api/safe/reset")
def safe_reset():
    db.reset_safe(request.get_json(force=True).get("group_url") or None)
    return jsonify({"ok": True})


# ---------- Sản phẩm ----------
def product_json(p):
    text = prod.fill_price(p["text"], p["price"], p.get("new_price"))
    safe = prod.fill_price(p["safe_text"], p["price"], p.get("new_price"))
    vs = db.variants(p["id"])
    return {**p, "text_preview": text, "safe_preview": safe or prod.make_safe(text), "safe_auto": not (p["safe_text"] or "").strip(),
            "image_ok": bool(p["image"]) and os.path.exists(os.path.join(Config.IMAGE_DIR, p["image"])),
            "variants_total": len(vs), "variants_active": sum(v["active"] for v in vs)}


def variant_json(v, p):
    text = prod.fill_price(v["text"], p["price"], p.get("new_price"))
    safe = prod.fill_price(v["safe_text"], p["price"], p.get("new_price"))
    return {**v, "text_preview": text, "safe_preview": safe or prod.make_safe(text), "safe_auto": not (v["safe_text"] or "").strip()}


@app.get("/api/products")
def products_list():
    return jsonify([product_json(p) for p in db.products()])


def product_fields(form, files, current=None):
    name = (form.get("name") or "").strip()
    if not name:
        raise ValueError("Cần nhập tên sản phẩm")
    fields = {"name": name, "price": (form.get("price") or "").strip(), "new_price": (form.get("new_price") or "").strip()}
    image = files.get("image")
    if image and image.filename:
        fields["image"] = prod.save_image(image, name, Config.IMAGE_DIR)
    elif not current:
        fields["image"] = ""
    return fields


@app.post("/api/products")
def products_add():
    try:
        fields = product_fields(request.form, request.files)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    pid = db.add_product(active=1 if request.form.get("active", "1") == "1" else 0, text="", safe_text="", **fields)
    text = (request.form.get("text") or "").strip()
    if text:  # mẫu bình luận đầu tiên
        db.add_variant(pid, text, (request.form.get("safe_text") or "").strip())
    return jsonify(product_json(db.get_product(pid)))


@app.post("/api/products/<int:pid>")
def products_update(pid):
    current = db.get_product(pid)
    if not current:
        return jsonify({"error": "Không tìm thấy sản phẩm"}), 404
    try:
        fields = product_fields(request.form, request.files, current)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    db.update_product(pid, **fields)
    return jsonify(product_json(db.get_product(pid)))


@app.post("/api/products/<int:pid>/active")
def products_active(pid):
    db.update_product(pid, active=1 if request.get_json(force=True).get("active") else 0)
    return jsonify({"ok": True})


@app.delete("/api/products/<int:pid>")
def products_delete(pid):
    db.delete_product(pid)  # ảnh vẫn giữ trong data/images (nhật ký bình luận cũ còn dùng)
    for v in db.variants(pid):
        db.delete_variant(v["id"])
    return jsonify({"ok": True})


# ---------- Mẫu bình luận (mỗi bài chọn ngẫu nhiên 1 mẫu / sản phẩm) ----------
@app.get("/api/products/<int:pid>/variants")
def variants_list(pid):
    p = db.get_product(pid)
    if not p:
        return jsonify([]), 404
    return jsonify([variant_json(v, p) for v in db.variants(pid)])


@app.post("/api/products/<int:pid>/variants")
def variants_add(pid):
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not db.get_product(pid) or not text:
        return jsonify({"error": "Cần nhập nội dung bình luận đầy đủ"}), 400
    vid = db.add_variant(pid, text, (data.get("safe_text") or "").strip())
    return jsonify({"id": vid})


@app.post("/api/products/<int:pid>/variants/active")
def variants_active_all(pid):
    on = 1 if request.get_json(force=True).get("active") else 0
    for v in db.variants(pid):
        db.update_variant(v["id"], active=on)
    return jsonify({"ok": True})


@app.post("/api/variants/<int:vid>")
def variants_update(vid):
    data = request.get_json(force=True)
    if not db.get_variant(vid):
        return jsonify({"error": "Không tìm thấy mẫu"}), 404
    fields = {}
    if "text" in data:
        if not str(data["text"]).strip():
            return jsonify({"error": "Nội dung bình luận đầy đủ không được để trống"}), 400
        fields["text"] = str(data["text"]).strip()
    if "safe_text" in data:
        fields["safe_text"] = str(data["safe_text"]).strip()
    if "active" in data:
        fields["active"] = 1 if data["active"] else 0
    if data.get("product_id") and db.get_product(int(data["product_id"])):
        fields["product_id"] = int(data["product_id"])  # chuyển mẫu sang sản phẩm khác
    if fields:
        db.update_variant(vid, **fields)
    return jsonify({"ok": True})


@app.delete("/api/variants/<int:vid>")
def variants_delete(vid):
    db.delete_variant(vid)
    return jsonify({"ok": True})


@app.post("/api/variants/import")
def variants_import():
    def read(field):
        f = request.files.get(field)
        if f and f.filename:
            return f.read().decode("utf-8-sig", errors="replace")
        return request.form.get(field + "_text") or ""
    full, safe = read("full"), read("safe")
    if not full.strip():
        return jsonify({"error": "Chưa chọn file (hoặc dán) bình luận đầy đủ"}), 400
    pid = request.form.get("product_id")
    added, per, unknown = prod.import_variants(db, full, safe, int(pid) if pid and pid.isdigit() else None)
    return jsonify({"added": added, "per_product": per, "unknown": unknown,
                    "blocks": len(prod.split_blocks(full)), "safe_blocks": len(prod.split_blocks(safe))})


# ---------- Danh sách nhóm (file Excel) ----------
@app.get("/api/lists")
def lists():
    joined = {gl.normalize_group_url(r["group_url"])
              for r in db.query("SELECT group_url FROM group_join WHERE status = 'Đã tham gia'")}
    result = []
    for lst in db.group_lists():
        rows = gl.read_list(lst, Config)
        result.append({**lst, "count": len(rows),
                       "joined": sum(gl.normalize_group_url(r["group_url"]) in joined for r in rows),
                       "hanoi": sum(r.get("region") == "Hà Nội" for r in rows),
                       "exists": os.path.exists(os.path.join(Config.BASE_DIR, lst["path"]))})
    used = usable_groups(gl.load_groups(db, Config), Config.STATUS_FILE)
    return jsonify({"lists": result, "total": len(used), "priority": sum(g["priority"] for g in used),
                    "target_region": Config.TARGET_REGION})


@app.get("/api/lists/<key>/groups")
def list_groups(key):
    lst = db.get_group_list(key)
    if not lst:
        return jsonify([]), 404
    joined = {gl.normalize_group_url(r["group_url"]): r["status"]
              for r in db.query("SELECT group_url, status FROM group_join")}
    prio = db.priority_urls()
    # hiện cả nhóm bị ẩn do "chỉ nhóm Hà Nội" để bạn sửa khu vực
    rows = [{**r, "group_url": gl.normalize_group_url(r["group_url"])}
            for r in gl.read_list(lst, Config, db.group_names(), apply_filter=False)]
    for r in rows:
        r["priority"] = r["group_url"] in prio
        r["hidden"] = bool(lst["region_filter"] and Config.TARGET_REGION and r.get("region") != Config.TARGET_REGION)
    rows = gl.group_priority(rows, Config)
    rows.sort(key=lambda r: r["hidden"])
    return jsonify([{"group_url": r["group_url"], "group_name": r.get("group_name", ""), "members": r.get("members", ""),
                     "activity": r.get("activity", ""), "region": r.get("region", ""), "priority": r["priority"],
                     "hidden": r["hidden"], "join": joined.get(r["group_url"], "")} for r in rows])


def _list_or_404(key):
    lst = db.get_group_list(key)
    if not lst:
        raise ValueError("Không tìm thấy danh sách")
    return lst


@app.post("/api/lists/new")
def lists_new():
    key = gl.create_list(db, Config, request.get_json(force=True).get("name") or "")
    return jsonify({"key": key})


@app.post("/api/lists/<key>/links")
def lists_add_links(key):
    try:
        added, dup, bad, hidden = gl.add_links(_list_or_404(key), Config, request.get_json(force=True).get("text", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"added": added, "dup": dup, "bad": bad, "hidden": hidden})


@app.post("/api/lists/<key>/groups/update")
def lists_group_update(key):
    data = request.get_json(force=True)
    try:
        url = gl.update_group(_list_or_404(key), Config, data.get("old_url", ""), data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"group_url": url})


@app.post("/api/lists/<key>/groups/delete")
def lists_group_delete(key):
    url = gl.normalize_group_url(request.get_json(force=True).get("group_url", ""))
    try:
        lst = _list_or_404(key)
        gl.delete_group(lst, Config, url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if lst["kind"] == "found":
        db.mark_removed(url)  # lần tìm nhóm sau không tự thêm lại
    return jsonify({"ok": True})


# ---------- Tiến trình & nhật ký ----------
def _script_alive(pid, *args):
    """Tiến trình pid còn chạy và là main.py (args: tham số dòng lệnh phải có, vd "quet")"""
    if not pid:
        return False
    try:
        cmd = psutil.Process(int(pid)).cmdline()
        return any("main.py" in a for a in cmd) and all(x in cmd for x in args)
    except (psutil.Error, ValueError):
        return False


def _age_seconds(updated_at):
    if not updated_at:
        return None
    return int((datetime.now() - datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")).total_seconds())


@app.get("/api/progress")
def progress():
    p = db.progress()
    scans = []
    for n in range(1, Config.SCAN_WINDOWS + 1):  # cửa sổ quét 1: "main.py quet", cửa sổ n: "main.py quet n"
        s = db.scan_progress(n)
        args = ("quet",) if n == 1 else ("quet", str(n))
        scans.append({**s, "n": n, "alive": _script_alive(s.get("pid"), *args), "age": _age_seconds(s.get("updated_at"))})
    return jsonify({**p, "alive": _script_alive(p.get("pid")), "age": _age_seconds(p.get("updated_at")),
                    "paused": db.is_paused(), "parallel": Config.PARALLEL, "scans": scans, "queue": db.queue_counts()})


LOG_NOISE = re.compile(r"WebDriver manager|found in cache|Retrying \(Retry|Get LATEST|There is no \[win")


@app.get("/api/log")
def log_tail():
    n = min(int(request.args.get("n", 150)), 1000)
    path = os.path.join(Config.LOG_DIR, "app.log")
    if not os.path.exists(path):
        return jsonify([])
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 300_000))
        lines = f.read().decode("utf-8", errors="replace").splitlines()[1:]
    lines = [l for l in lines if l.strip() and not LOG_NOISE.search(l)]
    return jsonify(lines[-n:])


@app.post("/api/groups/priority")
def group_set_priority():
    data = request.get_json(force=True)
    url = gl.normalize_group_url(data.get("group_url", ""))
    db.set_priority(url, data.get("group_name", ""), bool(data.get("priority")))
    return jsonify({"ok": True})


@app.post("/api/lists")
def lists_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Chưa chọn file"}), 400
    try:
        key, n = gl.save_uploaded(db, Config, f, request.form.get("name") or "")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Không đọc được file: {e}"}), 400
    return jsonify({"key": key, "count": n})


@app.post("/api/lists/<key>")
def lists_update(key):
    data = request.get_json(force=True)
    fields = {k: 1 if data[k] else 0 for k in ("enabled", "region_filter", "priority") if k in data}
    if "name" in data and str(data["name"]).strip():
        fields["name"] = str(data["name"]).strip()
    if fields:
        db.update_group_list(key, **fields)
    return jsonify({"ok": True})


@app.delete("/api/lists/<key>")
def lists_delete(key):
    lst = db.get_group_list(key)
    if not lst or lst["kind"] != "upload":
        return jsonify({"error": "Chỉ xóa được file đã tải lên"}), 400
    db.delete_group_list(key)
    path = os.path.join(Config.BASE_DIR, lst["path"])
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


@app.get("/lists/<key>.xlsx")
def list_download(key):
    lst = db.get_group_list(key)
    path = lst and os.path.join(Config.BASE_DIR, lst["path"])
    if not path or not os.path.exists(path):
        return "Không có file", 404
    return send_file(path, as_attachment=True, download_name=f"{prod.slug(lst['name'])}.xlsx")


@app.get("/screenshots/<path:name>")
def screenshot(name):
    return send_from_directory(Config.SCREENSHOT_DIR, name)


@app.get("/images/<path:name>")
def image(name):
    return send_from_directory(Config.IMAGE_DIR, name)


@app.get("/export.xlsx")
def export():
    buf = io.BytesIO()
    db.comments_table().to_excel(buf, index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"nhat_ky_binh_luan_{datetime.now():%Y%m%d_%H%M}.xlsx")


if __name__ == "__main__":
    print(f"Web quản lý: http://127.0.0.1:{Config.WEB_PORT}  (Ctrl+C để tắt)")
    app.run(host="127.0.0.1", port=Config.WEB_PORT, debug=False)
