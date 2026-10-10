"""
Mức độ tương tác của 1 bài trong bảng tin: số cảm xúc (reaction), bình luận, chia sẻ -> điểm tương tác
(reaction x w_reaction + comment x w_comment + share x w_share, trọng số trong config.ENGAGEMENT_WEIGHTS).

Facebook hiện (10/2026) hiển thị các con số ngay dưới nội dung bài, mỗi số 1 dòng, theo thứ tự cảm xúc → bình luận →
chia sẻ, số nào bằng 0 thì không hiện. Có cảm xúc thì ô bài có nút "Xem ai đã bày tỏ cảm xúc về tin này" và nhãn
"Thích: 2 người". Giao diện cũ ghi chữ: "45 bình luận", "6 lượt chia sẻ". Đọc được cả hai kiểu.
"""
import re
from dataclasses import dataclass

from modules import fb_selectors as sel
from modules.group_finder import parse_count

COUNT_LINE = re.compile(r"^[\d.,]+\s*[KkNnMm]?$")


@dataclass(frozen=True)
class Engagement:
    reactions: int = 0
    comments: int = 0
    shares: int = 0
    known: bool = True   # False = không định vị được phần số liệu dưới bài (số chỉ ước theo nhãn, có thể thiếu)


def engagement_score(e, weights):
    """Điểm tương tác theo trọng số {'reaction', 'comment', 'share'}"""
    return (e.reactions * weights.get("reaction", 1) + e.comments * weights.get("comment", 2)
            + e.shares * weights.get("share", 3))


def _label_reactions(labels):
    for label in labels:
        m = sel.REACTION_LABEL.match(label or "")
        if m:
            return parse_count(m.group(1))
    return None


def _lines_after_message(text, message):
    """Các dòng ngay sau nội dung bài trong chữ của ô bài viết; None nếu không tìm thấy nội dung"""
    lines = [l.strip() for l in (text or "").splitlines()]
    msg = [l.strip() for l in (message or "").splitlines() if l.strip()]
    if not msg or msg[0] not in lines:
        return None
    start = lines.index(msg[0])
    for i in range(start, len(lines)):
        if lines[i] == msg[-1]:
            return lines[i + 1:]
    return None


def _leading_counts(lines):
    """Các con số liền sau nội dung: [('bare'|'reactions'|'comments'|'shares', n)], dừng ở dòng chữ đầu tiên"""
    counts, reactions_next = [], False
    for line in lines:
        low = line.lower()
        if not line or low in sel.SEE_MORE_TEXTS:
            continue
        if low in sel.ALL_REACTIONS_TEXT:
            reactions_next = True
            continue
        m = sel.COMMENTS_TEXT.match(line)
        if m:
            counts.append(("comments", parse_count(m.group(1))))
            continue
        m = sel.SHARES_TEXT.match(line)
        if m:
            counts.append(("shares", parse_count(m.group(1))))
            continue
        if COUNT_LINE.match(line):
            counts.append(("reactions" if reactions_next else "bare", parse_count(line)))
            reactions_next = False
            continue
        break
    return counts


def parse_engagement(item_text, message_text, labels):
    """Engagement của 1 ô bài viết: item_text = chữ cả ô, message_text = chữ phần nội dung, labels = các aria-label"""
    labels = [l or "" for l in labels]
    label_reactions = _label_reactions(labels)
    visible_comments = sum(bool(sel.COMMENT_LABEL.match(l)) for l in labels)
    lines = _lines_after_message(item_text, message_text)
    if lines is None:  # không định vị được nội dung bài: chỉ ước theo nhãn
        return Engagement(label_reactions or 0, visible_comments, 0, known=False)

    counts = _leading_counts(lines)
    explicit = {kind: n for kind, n in counts if kind != "bare"}
    bare = [n for kind, n in counts if kind == "bare"]
    has_reactions = label_reactions is not None or any(l in sel.REACTION_SUMMARY_LABELS for l in labels)
    if "reactions" in explicit:
        reactions = explicit["reactions"]
    elif has_reactions and bare:
        reactions = bare.pop(0)
    else:
        reactions = label_reactions or 0
    comments = explicit["comments"] if "comments" in explicit else (bare.pop(0) if bare else 0)
    shares = explicit["shares"] if "shares" in explicit else (bare.pop(0) if bare else 0)
    return Engagement(reactions, max(comments, visible_comments), shares)
