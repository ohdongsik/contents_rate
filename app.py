from __future__ import annotations

import html
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass
class EvalResult:
    content_type: str
    url: str
    scores: Dict[str, float]
    reviews: Dict[str, str]
    overview: List[str]
    average: float
    summary: str
    notes: List[str]


def clamp_1_5(value: float) -> float:
    return max(1.0, min(5.0, value))


def round_half(value: float) -> float:
    return round(value * 2) / 2


def safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.replace(",", ""))
    except Exception:
        return None


def fetch_html(url: str) -> Tuple[str, List[str]]:
    notes: List[str] = []
    attempts = [
        {"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"},
        {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    ]

    if requests is not None:
        for idx, headers in enumerate(attempts, start=1):
            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    timeout=12,
                    allow_redirects=True,
                )
                if resp.ok and resp.text:
                    return resp.text, notes
                notes.append(f"수집 시도 {idx} 실패(HTTP {resp.status_code})")
            except Exception as exc:
                notes.append(f"수집 시도 {idx} 실패: {exc}")
            time.sleep(0.3)

    for idx, headers in enumerate(attempts, start=1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=12) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace"), notes
        except Exception as exc:
            notes.append(f"보조 수집 시도 {idx} 실패: {exc}")
        time.sleep(0.3)

    notes.append("URL 수집 실패로 제한된 평가를 수행했습니다.")
    return "", notes


def strip_tags(text: str) -> str:
    text = re.sub(r"<script[\\s\\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\\s+", " ", text)
    return text.strip()


def parse_images(html_text: str) -> List[Dict[str, object]]:
    images: List[Dict[str, object]] = []
    img_tags = re.findall(r"<img\\b[^>]*>", html_text, flags=re.IGNORECASE)
    for tag in img_tags:
        src = extract_attr(tag, "src")
        if not src:
            continue
        alt = extract_attr(tag, "alt") or ""
        width = safe_int(extract_attr(tag, "width"))
        height = safe_int(extract_attr(tag, "height"))
        images.append({"src": src, "alt": alt, "width": width, "height": height})

        srcset = extract_attr(tag, "srcset") or ""
        if srcset:
            for chunk in srcset.split(","):
                part = chunk.strip().split(" ")[0].strip()
                if part and not any(img["src"] == part for img in images):
                    images.append({"src": part, "alt": alt, "width": None, "height": None})

    og_images = re.findall(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html_text,
        flags=re.IGNORECASE,
    )
    for src in og_images[:20]:
        if not any(img["src"] == src for img in images):
            images.append({"src": src, "alt": "", "width": None, "height": None})
    return images


def extract_attr(tag: str, attr: str) -> str | None:
    pat = re.compile(rf'{attr}\\s*=\\s*["\']([^"\']+)["\']', flags=re.IGNORECASE)
    m = pat.search(tag)
    return m.group(1).strip() if m else None


def parse_links_count(html_text: str) -> int:
    return len(re.findall(r"<a\\b[^>]*href=", html_text, flags=re.IGNORECASE))


def parse_hashtags(text: str) -> List[str]:
    return re.findall(r"#([A-Za-z0-9_가-힣]{2,30})", text)


def extract_count(html_text: str, keys: List[str]) -> int | None:
    for key in keys:
        pat = re.compile(rf'{re.escape(key)}[^0-9]{{0,15}}([0-9]{{1,9}})', flags=re.IGNORECASE)
        m = pat.search(html_text)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def extract_meta(html_text: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def extract_json_ld_chunks(html_text: str) -> List[dict]:
    chunks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html_text,
        flags=re.IGNORECASE,
    )
    parsed: List[dict] = []
    for chunk in chunks:
        text = chunk.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                parsed.append(obj)
            elif isinstance(obj, list):
                parsed.extend([x for x in obj if isinstance(x, dict)])
        except Exception:
            continue
    return parsed


def coalesce(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def parse_common(html_text: str) -> Dict[str, object]:
    if not html_text:
        return {
            "text": "",
            "links": 0,
            "images": [],
            "hashtags": [],
            "likes": None,
            "comments": None,
            "title": "",
            "description": "",
            "json_ld_count": 0,
            "word_count": 0,
        }

    text = strip_tags(html_text)
    images = parse_images(html_text)
    links = parse_links_count(html_text)
    hashtags = parse_hashtags(text)
    likes = extract_count(html_text, ["like_count", "likes", "좋아요"])
    comments = extract_count(html_text, ["comment_count", "comments", "댓글"])
    json_ld = extract_json_ld_chunks(html_text)

    title_match = re.search(r"<title>([\s\S]*?)</title>", html_text, flags=re.IGNORECASE)
    title_tag = html.unescape(title_match.group(1)).strip() if title_match else ""
    title = coalesce(extract_meta(html_text, "og:title"), title_tag)
    description = coalesce(
        extract_meta(html_text, "og:description"),
        extract_meta(html_text, "description"),
    )

    for obj in json_ld:
        article_body = obj.get("articleBody")
        caption = obj.get("caption")
        desc = obj.get("description")
        keywords = obj.get("keywords")
        for candidate in [article_body, caption, desc]:
            if isinstance(candidate, str) and candidate.strip() and candidate not in text:
                text = f"{text} {candidate.strip()}".strip()
        if isinstance(keywords, str):
            hashtags.extend([w.strip().lstrip("#") for w in keywords.split(",") if w.strip()])

    hashtags = [h for h in hashtags if len(h) >= 2]
    hashtags = list(dict.fromkeys(hashtags))[:80]

    if likes is None:
        likes = extract_count(html_text, ["edge_media_preview_like", "likeCount", "reaction_count"])
    if comments is None:
        comments = extract_count(html_text, ["edge_media_to_comment", "commentCount"])

    return {
        "text": text,
        "links": links,
        "images": images,
        "hashtags": hashtags,
        "likes": likes,
        "comments": comments,
        "title": title,
        "description": description,
        "json_ld_count": len(json_ld),
        "word_count": len(text.split()),
    }


def snippet(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean or "본문 텍스트를 충분히 추출하지 못했습니다."
    return clean[:limit].rstrip() + "..."


def score_label(score: float) -> str:
    if score >= 4.5:
        return "매우 우수"
    if score >= 3.5:
        return "양호"
    if score >= 2.5:
        return "보통"
    return "개선 필요"


def build_item_review(item: str, score: float, basis: str) -> str:
    diagnosis = {
        "매우 우수": "핵심 지표에서 높은 신뢰도를 보였습니다",
        "양호": "기본 완성도는 충분하지만 더 정교한 보강 여지가 있습니다",
        "보통": "품질이 균일하지 않아 강점과 약점이 함께 관찰됩니다",
        "개선 필요": "현재 데이터 기준으로 보완 우선순위가 높은 상태입니다",
    }
    label = score_label(score)
    return f"{label} ({score:.1f}/5). {diagnosis[label]}. {basis}"


def detect_place_clues(text: str) -> str:
    place_words = [
        "카페", "레스토랑", "해변", "공원", "스튜디오", "호텔", "거리", "매장", "오피스", "집",
        "seoul", "busan", "tokyo", "paris", "new york", "beach", "cafe", "restaurant", "studio",
    ]
    hits = [w for w in place_words if w.lower() in text.lower()]
    if not hits:
        return "장소 단서를 명확히 확인하지 못했습니다."
    uniq = ", ".join(sorted(set(hits))[:4])
    return f"배경 장소 단서: {uniq}"


def detect_product_focus(text: str, hashtags: List[str]) -> str:
    product_words = ["제품", "브랜드", "신상", "리뷰", "광고", "협찬", "출시", "model", "review", "brand"]
    has_product_word = any(w.lower() in text.lower() for w in product_words)
    product_tags = [h for h in hashtags if any(k in h.lower() for k in ["ad", "review", "brand", "item", "제품", "리뷰"])]
    if has_product_word or product_tags:
        tag_preview = ", ".join(product_tags[:3]) if product_tags else "관련 키워드 기반"
        return f"제품 주목성은 감지됨 ({tag_preview})."
    return "제품 중심 메시지는 상대적으로 약하거나 확인되지 않았습니다."


def build_blog_overview(parsed: Dict[str, object]) -> List[str]:
    text = str(parsed["text"])
    images = parsed["images"]
    image_with_alt = sum(1 for img in images if str(img.get("alt") or "").strip())
    title = str(parsed.get("title") or "")
    desc = str(parsed.get("description") or "")
    image_types = "일반 이미지"
    if images:
        hi_res = sum(
            1
            for img in images
            if isinstance(img.get("width"), int)
            and isinstance(img.get("height"), int)
            and int(img["width"]) >= 500
            and int(img["height"]) >= 500
        )
        image_types = f"고해상도 추정 {hi_res}장 / 전체 {len(images)}장"
    return [
        f"페이지 제목/설명: {snippet(coalesce(title, desc), 120)}",
        f"포스팅 내용 요약: {snippet(text, 200)}",
        f"첨부 이미지 요약: {image_types}, 대체텍스트(alt) 포함 {image_with_alt}장, 구조화데이터(JSON-LD) {parsed.get('json_ld_count', 0)}개",
    ]


def build_insta_overview(parsed: Dict[str, object]) -> List[str]:
    text = str(parsed["text"])
    images = parsed["images"]
    hashtags = parsed["hashtags"]
    title = str(parsed.get("title") or "")
    desc = str(parsed.get("description") or "")
    portrait_clues = len(re.findall(r"(portrait|face|selfie|인물|셀카)", text, flags=re.IGNORECASE))
    return [
        f"포스트 핵심 문구: {snippet(coalesce(desc, title, text), 120)}",
        f"이미지 배경 장소: {detect_place_clues(text)}",
        f"인물 전반 평가: 인물/셀카 단서 {portrait_clues}건, 이미지 수 {len(images)}장 기반으로 시각 연출 품질을 판정했습니다.",
        f"제품 주목성: {detect_product_focus(text, hashtags)}",
    ]


def build_blog_reviews(scores: Dict[str, float], parsed: Dict[str, object]) -> Dict[str, str]:
    text = str(parsed["text"])
    images = parsed["images"]
    links = int(parsed["links"])
    words = int(parsed.get("word_count", 0))
    json_ld_count = int(parsed.get("json_ld_count", 0))
    return {
        "이미지 퀄리티": build_item_review(
            "이미지 퀄리티",
            scores["이미지 퀄리티"],
            (
                f"이미지 {len(images)}장을 확인했고 alt 텍스트 {sum(1 for i in images if i.get('alt'))}장,"
                " srcset/og:image 후보까지 포함해 시각 자료 밀도와 설명력을 평가했습니다."
            ),
        ),
        "진정성/객관성": build_item_review(
            "진정성/객관성",
            scores["진정성/객관성"],
            (
                f"본문 약 {words}단어, 참고 링크 {links}개, 주관/객관 단어 균형을 근거로"
                " 개인 경험과 정보 전달의 균형도를 판정했습니다."
            ),
        ),
        "내러티브": build_item_review(
            "내러티브",
            scores["내러티브"],
            "문장 길이 분포, 전개 접속어(처음/다음/결론) 존재, 도입-전개-정리 흐름의 일관성을 종합했습니다.",
        ),
        "맞춤법/표기": build_item_review(
            "맞춤법/표기",
            scores["맞춤법/표기"],
            "반복 문장부호, 비정상 공백, 자모 반복 패턴과 문장 가독성을 함께 반영해 표기 안정성을 계산했습니다.",
        ),
        "정보 사실성": build_item_review(
            "정보 사실성",
            scores["정보 사실성"],
            (
                f"숫자/날짜/출처 단서, 링크 {links}개, JSON-LD {json_ld_count}개를 근거로"
                " 검증 가능한 정보의 비율을 평가했습니다."
            ),
        ),
    }


def build_insta_reviews(scores: Dict[str, float], parsed: Dict[str, object]) -> Dict[str, str]:
    images = parsed["images"]
    hashtags = parsed["hashtags"]
    likes = parsed["likes"]
    comments = parsed["comments"]
    title = str(parsed.get("title") or "")
    desc = str(parsed.get("description") or "")
    text_hint = coalesce(desc, title)
    return {
        "피사체 퀄리티": build_item_review(
            "피사체 퀄리티",
            scores["피사체 퀄리티"],
            (
                f"이미지 {len(images)}장의 수량, 해상도 단서, 대체텍스트 구성도를 종합해"
                " 프레이밍/피사체 선명도를 간접 추정했습니다."
            ),
        ),
        "인물 표현 점수": build_item_review(
            "인물 표현 점수",
            scores["인물 표현 점수"],
            (
                "인물/셀카 키워드, 포스트 설명문, 이미지 설명을 결합해"
                " 인물 중심 연출의 일관성과 전달력을 판단했습니다."
            ),
        ),
        "해시태그 희소성": build_item_review(
            "해시태그 희소성",
            scores["해시태그 희소성"],
            (
                f"해시태그 {len(hashtags)}개의 고유 비율과 길이, 범용 태그 편중도를 바탕으로"
                " 검색 경쟁 회피 가능성을 평가했습니다."
            ),
        ),
        "좋아요/댓글 반응": build_item_review(
            "좋아요/댓글 반응",
            scores["좋아요/댓글 반응"],
            (
                f"좋아요 {likes if likes is not None else '미확인'}, 댓글 {comments if comments is not None else '미확인'}를"
                f" 반영했고, 설명문 단서('{snippet(text_hint, 40)}')와의 적합도도 참고했습니다."
            ),
        ),
    }


def sentence_stats(text: str) -> Tuple[int, float]:
    if not text:
        return 0, 0.0
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 2]
    if not sentences:
        return 0, 0.0
    avg_len = sum(len(s) for s in sentences) / len(sentences)
    return len(sentences), avg_len


def score_image_quality(images: List[Dict[str, object]]) -> float:
    if not images:
        return 2.0

    count_score = min(2.0, len(images) / 5)
    sized = 0
    with_alt = 0
    for img in images:
        w = img.get("width")
        h = img.get("height")
        if isinstance(w, int) and isinstance(h, int) and w >= 500 and h >= 500:
            sized += 1
        if img.get("alt"):
            with_alt += 1

    size_score = min(1.5, sized / max(1, len(images)) * 1.5)
    alt_score = min(1.5, with_alt / max(1, len(images)) * 1.5)
    return clamp_1_5(1.0 + count_score + size_score + alt_score)


def score_blog_sincerity_objectivity(text: str, links: int) -> float:
    if not text:
        return 2.0

    objectivity_keywords = ["장점", "단점", "비교", "근거", "수치", "후기", "개인적", "주관", "객관"]
    keyword_hits = sum(1 for kw in objectivity_keywords if kw in text)
    keyword_score = min(2.0, keyword_hits * 0.25)
    link_score = min(1.0, links * 0.2)

    first_person_ratio = len(re.findall(r"(저|제가|나는|내가)", text)) / max(1.0, len(text) / 50)
    balance_score = 1.0 if 0.2 <= first_person_ratio <= 2.5 else 0.6

    return clamp_1_5(1.2 + keyword_score + link_score + balance_score)


def score_blog_narrative(text: str) -> float:
    sentence_count, avg_len = sentence_stats(text)
    if sentence_count == 0:
        return 1.8

    structure_words = ["처음", "먼저", "다음", "그리고", "결론", "정리", "마지막"]
    structure_hits = sum(1 for w in structure_words if w in text)

    sentence_score = 1.0 if 6 <= sentence_count <= 80 else 0.6
    length_score = 1.2 if 20 <= avg_len <= 70 else 0.7
    structure_score = min(1.8, structure_hits * 0.35)

    return clamp_1_5(1.0 + sentence_score + length_score + structure_score)


def score_blog_spelling(text: str) -> float:
    if not text:
        return 2.2

    weird_spaces = len(re.findall(r"\\s{2,}", text))
    repeated_punct = len(re.findall(r"[!?.,]{3,}", text))
    typo_like = len(re.findall(r"[ㄱ-ㅎㅏ-ㅣ]{3,}", text))

    penalties = weird_spaces * 0.1 + repeated_punct * 0.25 + typo_like * 0.25
    base = 4.6 - min(3.2, penalties)
    return clamp_1_5(base)


def score_blog_factuality(text: str, links: int) -> float:
    if not text:
        return 2.0

    date_hits = len(re.findall(r"20\\d{2}[./년-]\\s?\\d{1,2}", text))
    number_hits = len(re.findall(r"\\d+[.,]?\\d*", text))
    source_words = ["출처", "통계", "공식", "자료", "리포트", "논문"]
    source_hits = sum(1 for w in source_words if w in text)

    evidence_score = min(2.5, date_hits * 0.5 + number_hits * 0.05 + source_hits * 0.5)
    link_score = min(1.0, links * 0.2)
    return clamp_1_5(1.0 + evidence_score + link_score)


def score_insta_subject(images: List[Dict[str, object]]) -> float:
    return score_image_quality(images)


def score_insta_appearance(text: str, images: List[Dict[str, object]]) -> float:
    if not images:
        return 2.5

    portrait_clues = len(re.findall(r"(portrait|face|selfie|인물|셀카)", text, flags=re.IGNORECASE))
    rich_alt = sum(1 for img in images if len(str(img.get("alt") or "")) >= 8)
    return clamp_1_5(2.0 + min(1.5, portrait_clues * 0.3) + min(1.5, rich_alt * 0.25))


def score_insta_hashtag_rarity(hashtags: List[str]) -> float:
    if not hashtags:
        return 2.0

    uniq = len(set(hashtags))
    avg_len = sum(len(h) for h in hashtags) / len(hashtags)
    short_generic = sum(1 for h in hashtags if len(h) <= 3)

    uniq_score = min(2.2, uniq / max(1, len(hashtags)) * 2.2)
    len_score = 1.2 if avg_len >= 6 else 0.7
    generic_penalty = min(1.2, short_generic * 0.2)

    return clamp_1_5(1.3 + uniq_score + len_score - generic_penalty)


def score_insta_engagement(likes: int | None, comments: int | None) -> float:
    if likes is None and comments is None:
        return 3.0

    like_part = 0.0 if likes is None else min(2.0, math.log10(max(1, likes)) * 0.8)
    comment_part = 0.0 if comments is None else min(2.0, math.log10(max(1, comments + 1)) * 1.0)

    return clamp_1_5(1.0 + like_part + comment_part)


def build_summary(content_type: str, avg: float, scores: Dict[str, float]) -> str:
    if avg >= 4.3:
        tone = "완성도가 높고 신뢰 가능한 콘텐츠입니다."
    elif avg >= 3.4:
        tone = "전반적으로 안정적이지만 일부 개선 여지가 있습니다."
    else:
        tone = "핵심 품질 지표에서 보완이 필요합니다."

    weakest = min(scores, key=scores.get)
    strongest = max(scores, key=scores.get)

    return (
        f"Sally 평가 결과, {tone} "
        f"강점은 '{strongest}' 항목이고 개선 우선순위는 '{weakest}' 항목입니다. "
        f"유형: {content_type}"
    )


def evaluate(content_type: str, url: str) -> EvalResult:
    html_text, notes = fetch_html(url)
    parsed = parse_common(html_text)

    if content_type == "instagram":
        scores = {
            "피사체 퀄리티": round_half(score_insta_subject(parsed["images"])),
            "인물 표현 점수": round_half(score_insta_appearance(parsed["text"], parsed["images"])),
            "해시태그 희소성": round_half(score_insta_hashtag_rarity(parsed["hashtags"])),
            "좋아요/댓글 반응": round_half(score_insta_engagement(parsed["likes"], parsed["comments"])),
        }
        reviews = build_insta_reviews(scores, parsed)
        overview = build_insta_overview(parsed)
        avg = round_half(sum(scores.values()) / len(scores))
        summary = build_summary("인스타그램 피드", avg, scores)
        return EvalResult("인스타그램 피드", url, scores, reviews, overview, avg, summary, notes)

    scores = {
        "이미지 퀄리티": round_half(score_image_quality(parsed["images"])),
        "진정성/객관성": round_half(score_blog_sincerity_objectivity(parsed["text"], parsed["links"])),
        "내러티브": round_half(score_blog_narrative(parsed["text"])),
        "맞춤법/표기": round_half(score_blog_spelling(parsed["text"])),
        "정보 사실성": round_half(score_blog_factuality(parsed["text"], parsed["links"])),
    }
    reviews = build_blog_reviews(scores, parsed)
    overview = build_blog_overview(parsed)
    avg = round_half(sum(scores.values()) / len(scores))
    summary = build_summary("네이버 블로그 포스팅", avg, scores)
    return EvalResult("네이버 블로그 포스팅", url, scores, reviews, overview, avg, summary, notes)


def render_page(result: EvalResult | None = None, error: str = "") -> str:
    style = """
    <style>
      :root { --bg:#f4f7fb; --card:#fff; --text:#102a43; --muted:#486581; --line:#d9e2ec; --ok:#0b6e4f; --err:#b42318; }
      * { box-sizing: border-box; }
      body { margin:0; font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif; background:radial-gradient(circle at top right,#d9f7e7 0%,var(--bg) 45%); color:var(--text); }
      .wrap { max-width:920px; margin:28px auto; padding:0 16px; display:grid; gap:16px; }
      .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; box-shadow:0 8px 24px rgba(16,42,67,.08); }
      h1,h2,h3 { margin:0 0 12px; }
      .sub { margin:0 0 14px; color:var(--muted); }
      .form { display:grid; gap:10px; }
      label { font-weight:700; }
      input,select,button { font-size:16px; padding:10px; border-radius:10px; }
      input,select { border:1px solid var(--line); }
      button { border:none; background:var(--ok); color:#fff; font-weight:700; cursor:pointer; }
      .err { color:var(--err); font-weight:700; }
      table { width:100%; border-collapse:collapse; }
      th,td { text-align:left; border-bottom:1px solid var(--line); padding:9px 6px; }
      .avg { font-size:20px; font-weight:800; margin-top:12px; }
      .notes { margin-top:12px; background:#f8fafc; border:1px solid var(--line); border-radius:10px; padding:10px; }
      .overview { margin:12px 0; background:#f8fafc; border:1px solid var(--line); border-radius:10px; padding:10px; }
      .review { color:var(--muted); font-size:14px; line-height:1.45; }
    </style>
    """

    form_html = """
    <div class='card'>
      <h1>Sally 콘텐츠 평가기</h1>
      <p class='sub'>URL을 입력하면 동일한 루브릭으로 항목별 별점(1~5)과 평균 점수를 계산합니다.</p>
      <form class='form' method='post'>
        <label for='content_type'>콘텐츠 유형</label>
        <select id='content_type' name='content_type'>
          <option value='blog'>네이버 블로그 포스팅</option>
          <option value='instagram'>인스타그램 피드</option>
        </select>

        <label for='url'>콘텐츠 URL</label>
        <input id='url' name='url' type='url' required placeholder='https://...' />

        <button type='submit'>Sally 평가 실행</button>
      </form>
      {error_block}
    </div>
    """

    error_block = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    result_block = ""

    if result:
        rows = "".join(
            (
                f"<tr><td>{html.escape(k)}"
                f"<div class='review'>{html.escape(result.reviews.get(k, ''))}</div>"
                f"</td><td>{v:.1f} / 5</td></tr>"
            )
            for k, v in result.scores.items()
        )
        overview_items = "".join(f"<li>{html.escape(item)}</li>" for item in result.overview)
        overview_block = f"<div class='overview'><h3>콘텐츠 요약정보</h3><ul>{overview_items}</ul></div>"
        notes_block = ""
        if result.notes:
            notes_items = "".join(f"<li>{html.escape(n)}</li>" for n in result.notes)
            notes_block = f"<div class='notes'><h3>참고</h3><ul>{notes_items}</ul></div>"

        result_block = f"""
        <div class='card'>
          <h2>평가 결과</h2>
          <p><strong>유형:</strong> {html.escape(result.content_type)}</p>
          <p><strong>URL:</strong> <a href='{html.escape(result.url)}' target='_blank'>{html.escape(result.url)}</a></p>
          {overview_block}
          <table>
            <thead><tr><th>평가 항목 및 심사평</th><th>별점</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <p class='avg'>평균 별점: {result.average:.1f} / 5</p>
          <p>{html.escape(result.summary)}</p>
          {notes_block}
        </div>
        """

    page = f"""
    <!doctype html>
    <html lang='ko'>
      <head>
        <meta charset='utf-8' />
        <meta name='viewport' content='width=device-width, initial-scale=1' />
        <title>Sally 콘텐츠 별점 평가</title>
        {style}
      </head>
      <body>
        <main class='wrap'>
          {form_html.format(error_block=error_block)}
          {result_block}
        </main>
      </body>
    </html>
    """
    return page


class SallyHandler(BaseHTTPRequestHandler):
    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        self._send_html(render_page())

    def do_POST(self) -> None:  # noqa: N802
        content_len = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_len).decode("utf-8", errors="replace")
        data = parse_qs(raw)

        content_type = (data.get("content_type", ["blog"])[0] or "blog").strip()
        url = (data.get("url", [""])[0] or "").strip()

        error = ""
        result = None

        parsed = urlparse(url)
        if not url:
            error = "URL을 입력해 주세요."
        elif parsed.scheme not in ("http", "https"):
            error = "http:// 또는 https:// URL만 지원합니다."
        else:
            result = evaluate(content_type, url)

        self._send_html(render_page(result=result, error=error))


def run_server(host: str = HOST, port: int = PORT) -> None:
    server = HTTPServer((host, port), SallyHandler)
    print(f"Sally 평가기 실행: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    host = HOST
    port = PORT
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        try:
            port = int(sys.argv[2])
        except ValueError:
            pass
    run_server(host=host, port=port)
