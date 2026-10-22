"""Gửi bình luận: lần bấm Enter đầu chưa gửi được (ô soạn vẫn còn chữ, thường do ảnh tải lên chậm) -> bấm lại 1 lần
(20/10: 5 bình luận kèm ảnh mỗi bài, bình luận thứ 4 báo "không gửi được (ô soạn vẫn còn chữ)")."""
from types import SimpleNamespace

from modules import commenter as cm
from modules.db import SENT


def fake_commenter(monkeypatch, cleared, shown_after_first=False):
    clock = [0.0]
    monkeypatch.setattr(cm, "time", SimpleNamespace(sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                                                    time=lambda: clock[0]))
    c = cm.FacebookCommenter(driver=None, config=SimpleNamespace())
    editor = SimpleNamespace(text="Nội dung")
    enters, waits = [], iter(cleared)
    c._focus_editor = lambda: editor
    c._type_text = lambda e, text: e
    c._find_editor = lambda: editor
    c._attach_image = lambda e, path: ""
    c._send_keys = lambda e, *keys: (enters.append(keys), e)[1]
    c._wait_editor_cleared = lambda e, timeout=20: next(waits)
    c._notices = lambda: ""
    article = SimpleNamespace(text="Nội dung")
    c.find_comment = lambda text: article if (shown_after_first or len(enters) > 1) else None
    c.is_rejected = lambda art: False
    return c, enters


def test_enter_is_pressed_again_when_first_one_did_not_send(monkeypatch):
    c, enters = fake_commenter(monkeypatch, cleared=[False, True])
    status, _ = c.send_comment({"text": "Nội dung", "image": "anh.png"})
    assert status == SENT and len(enters) == 2


def test_no_second_enter_when_comment_already_shows(monkeypatch):
    c, enters = fake_commenter(monkeypatch, cleared=[False], shown_after_first=True)
    status, _ = c.send_comment({"text": "Nội dung", "image": "anh.png"})
    assert status == SENT and len(enters) == 1          # đã hiện trên bài: không gửi trùng
