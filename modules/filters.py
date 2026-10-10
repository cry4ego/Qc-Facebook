"""
Bộ lọc quyết định bình luận — mỗi tiêu chí là 1 hàm nhỏ trả về Verdict(ok, lý do).

  POST_FILTERS  : áp cho từng bài trong bảng tin (chủ đề → ý định MUA/BÁN → khu vực → điểm tương tác)
  GROUP_FILTERS : áp cho từng nhóm trước khi quét (số thành viên → số bài mỗi ngày)

Bộ lọc chạy theo thứ tự, dừng ở tiêu chí đầu tiên không đạt — tiêu chí tốn công (đọc tương tác trên trang) đặt sau
cùng nên chỉ chạy khi các tiêu chí trước đã đạt. Muốn thêm tiêu chí mới: viết 1 hàm (subject, config) -> Verdict
rồi thêm vào danh sách, không phải sửa luồng quét / bình luận.
"""
from dataclasses import dataclass, replace
from functools import cached_property

from modules.engagement import engagement_score
from modules.intent import BUY, UNKNOWN, classify_intent, load_rules
from modules.region import find_regions, load_regions
from modules.topic import topic


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""


class PostCandidate:
    """1 bài trong bảng tin. Thông tin được tính khi bộ lọc cần tới (read_engagement chỉ gọi nếu cần)"""

    def __init__(self, text, age, config, read_engagement, ai=None, hanoi_group=False):
        self.text = text
        self.age = age
        self.config = config
        self._read_engagement = read_engagement
        self._ai = ai  # AiIntent (Gemini) — chỉ hỏi khi từ khóa chấm KHÔNG XÁC ĐỊNH
        self.hanoi_group = hanoi_group  # bài nằm trong nhóm Hà Nội (không ghi khu vực = coi là khách Hà Nội)

    def computed(self, name):
        """Giá trị đã được tính (None nếu bộ lọc chưa cần tới — vd bài bán thì không đọc tương tác)"""
        return self.__dict__.get(name)

    @cached_property
    def topic(self):
        return topic(self.text)

    @cached_property
    def intent(self):
        rules = load_rules(self.config.INTENT_KEYWORDS_FILE)
        result = classify_intent(self.text, rules, self.config.INTENT_MIN_SCORE, self.config.INTENT_MARGIN)
        if result.label == UNKNOWN and self._ai:
            verdict = self._ai(self.text)
            if verdict:
                return replace(result, label=verdict.label, ai_reason=verdict.reason or "—")
        return result

    @cached_property
    def region(self):
        return find_regions(self.text, load_regions(self.config.REGION_FILE))

    @cached_property
    def engagement(self):
        return self._read_engagement()

    @cached_property
    def score(self):
        return engagement_score(self.engagement, self.config.ENGAGEMENT_WEIGHTS)


# ---------- Tiêu chí cho bài viết ----------
def topic_filter(post, config):
    name = post.topic or "không liên quan"
    if not config.COMMENT_TOPICS or post.topic in config.COMMENT_TOPICS:
        return Verdict(True, f"chủ đề {name}")
    return Verdict(False, f"chủ đề {name} (chỉ bình luận: {', '.join(config.COMMENT_TOPICS)})")


def intent_filter(post, config):
    if not config.INTENT_FILTER:
        return Verdict(True, "không lọc ý định (INTENT_FILTER = False)")
    return Verdict(post.intent.label == BUY, post.intent.reason)


def region_filter(post, config):
    """Khách ghi rõ ở khu vực xa (TP.HCM, tỉnh xa…) thì bỏ qua. Bài không ghi khu vực: nhóm Hà Nội vẫn bình luận,
    nhóm toàn quốc thì bỏ qua (REGION_REQUIRED_IN_NATIONAL_GROUPS — khoảng một nửa là khách tỉnh xa)"""
    if not config.REGION_FILTER:
        return Verdict(True, "")
    r = post.region
    if r.is_far:
        return Verdict(False, f"khách ở xa ({', '.join(r.far)}) — chỉ bình luận khách Hà Nội & lân cận")
    if r.near:
        return Verdict(True, f"khu vực {', '.join(r.near)}")
    if post.hanoi_group:
        return Verdict(True, "không ghi khu vực, nhóm Hà Nội")
    if config.REGION_REQUIRED_IN_NATIONAL_GROUPS:
        return Verdict(False, "không ghi khu vực (nhóm toàn quốc — chỉ bình luận bài ghi Hà Nội / tỉnh lân cận)")
    return Verdict(True, "")


def engagement_filter(post, config):
    need = config.POST_MIN_ENGAGEMENT
    if need <= 0:
        return Verdict(True, "")  # không xét tương tác: bình luận ngay, không tốn công đọc số liệu
    e = post.engagement
    counts = f"({e.reactions} cảm xúc, {e.comments} bình luận, {e.shares} chia sẻ)"
    if post.score >= need:
        return Verdict(True, f"điểm tương tác {post.score:g} ≥ {need:g} {counts}")
    if not e.known:  # không đọc chắc được số liệu (giao diện lạ): không coi là 0 — cho qua, ghi rõ để kiểm tra
        return Verdict(True, f"không đọc chắc được tương tác (ước {post.score:g}) {counts} — vẫn cho qua")
    return Verdict(False, f"điểm tương tác {post.score:g} < {need:g} {counts}")


POST_FILTERS = [topic_filter, intent_filter, region_filter, engagement_filter]


# ---------- Tiêu chí cho nhóm (stats: dict từ bảng group_stats, có thể None) ----------
def members_filter(stats, config):
    if not stats or stats.get("members") is None:
        why = (stats or {}).get("error") or "chưa có dữ liệu"
        return Verdict(False, f"không lấy được số thành viên ({why})")
    hanoi = bool(stats.get("hanoi"))  # người gọi đánh dấu nhóm Hà Nội (group_finder.is_hanoi_group): cần ít thành viên hơn
    n = stats["members"]
    need = config.GROUP_MIN_MEMBERS_HANOI if hanoi else config.GROUP_MIN_MEMBERS
    ok = n >= need
    label = " (nhóm Hà Nội)" if hanoi else ""
    return Verdict(ok, f"{n:,} thành viên {'≥' if ok else '<'} {need:,}".replace(",", ".") + label)


def activity_filter(stats, config):
    need = config.GROUP_MIN_POSTS_PER_DAY
    if not need:
        return Verdict(True, "")
    posts = (stats or {}).get("posts_today")
    if posts is None:
        return Verdict(True, "trang Giới thiệu không ghi số bài/ngày")
    ok = posts >= need
    return Verdict(ok, f"{posts} bài/ngày {'≥' if ok else '<'} {need}")


GROUP_FILTERS = [members_filter, activity_filter]


def run_filters(filters, subject, config):
    """Chạy lần lượt các tiêu chí; trả về Verdict của tiêu chí đầu tiên không đạt, hoặc đạt kèm mọi lý do"""
    reasons = []
    for f in filters:
        v = f(subject, config)
        if not v.ok:
            return v
        if v.reason:
            reasons.append(v.reason)
    return Verdict(True, " · ".join(reasons))
