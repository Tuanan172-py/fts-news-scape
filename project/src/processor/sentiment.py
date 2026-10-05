"""Công cụ phân tích và chấm điểm sắc thái tin tức tài chính dựa trên bộ từ điển (Lexicon Engine)."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.processor.segment import seg

NEGATIONS = {"không", "chưa", "chẳng", "không_phải", "chưa_thể", "không_còn"}

_LABEL_POS = "positive"
_LABEL_NEG = "negative"
_LABEL_NEU = "neutral"


def _load_tsv(path: Path) -> dict[str, float]:
    lex: dict[str, float] = {}
    if not path.exists():
        logger.warning("Lexicon file missing: {}", path)
        return lex
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        try:
            lex[parts[0].strip().lower()] = float(parts[1])
        except ValueError:
            continue
    return lex


class SentimentEngine:
    """Động cơ tính toán điểm phân cực cảm xúc cho tiêu đề và nội dung bài viết.

    Attributes:
        lex: Từ điển ánh xạ từ khóa sang điểm sắc thái.
        pos_threshold: Ngưỡng điểm xác định sắc thái tích cực.
        neg_threshold: Ngưỡng điểm xác định sắc thái tiêu cực.
    """

    def __init__(self, lexicon_dir: str = "data/lexicon",
                 pos_threshold: float = 0.2, neg_threshold: float = -0.2):
        d = Path(lexicon_dir)
        self.lex = _load_tsv(d / "vswn_polarity.tsv")
        self.lex.update(_load_tsv(d / "finance_terms.tsv"))
        self.pos_threshold = pos_threshold
        self.neg_threshold = neg_threshold
        logger.info("SentimentEngine loaded {} lexicon entries", len(self.lex))

    def score_tokens(self, tokens: list[str]) -> float:
        """Tính điểm sắc thái trung bình cho danh sách token theo thứ tự ưu tiên n-gram dài nhất.

        Args:
            tokens: Danh sách các từ hoặc token đã phân đoạn.

        Returns:
            Điểm số sắc thái trung bình dạng số thực.
        """
        tokens = [t.lower() for t in tokens]
        scores: list[float] = []
        i = 0
        while i < len(tokens):
            matched = False
            for n in (3, 2, 1):
                if i + n > len(tokens):
                    continue
                key = "_".join(tokens[i:i + n])
                s = self.lex.get(key)
                if s is None:
                    continue
                if i > 0 and tokens[i - 1] in NEGATIONS:
                    s = -s
                scores.append(s)
                i += n
                matched = True
                break
            if not matched:
                i += 1
        return sum(scores) / len(scores) if scores else 0.0

    def analyze(self, title: str, text: str = "") -> tuple[str, float]:
        """Phân tích sắc thái của bài viết kết hợp tiêu đề và nội dung.

        Args:
            title: Tiêu đề bài viết.
            text: Nội dung văn bản của bài viết.

        Returns:
            Bộ (nhãn sắc thái, điểm số) với nhãn thuộc positive, negative hoặc neutral.
        """
        title_score = self.score_tokens(seg(title))
        body_score = self.score_tokens(seg(text)[:100]) if text else 0.0
        if text:
            score = 0.67 * title_score + 0.33 * body_score
        else:
            score = title_score
        score = round(score, 3)
        if score > self.pos_threshold:
            return _LABEL_POS, score
        if score < self.neg_threshold:
            return _LABEL_NEG, score
        return _LABEL_NEU, score
