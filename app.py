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
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urljoin, urlparse
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

BLOG_RUBRIC = [
    "등록한 이미지의 퀄리티",
    "작성한 블로그 포스팅 내용의 진정성 및 객관적 평가",
    "작성한 글의 내러티브 평가",
    "작성한 글의 맞춤법, 띄어쓰기등 표기 오류",
    "작성한 글의 정보의 사실성",
]

INSTAGRAM_RUBRIC = [
    "등록한 이미지의 피사체의 퀄리티",
    "등록한 이미지의 인물의 외모 점수",
    "등록한 해시태그의 희소성",
    "등록한 인스타그램 계정의 좋아요, 댓글등 반응",
]


@dataclass
class EvalResult:
    content_type: str
    url: str
    scores: Dict[str, float]
    reviews: Dict[str, str]
    overview: List[str]
    dashboard: Dict[str, str]
    token_usage: Dict[str, str]
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

    final_html = ""
    final_url = url

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
                    final_html = resp.text
                    final_url = resp.url
                    break
                notes.append(f"수집 시도 {idx} 실패(HTTP {resp.status_code})")
            except Exception as exc:
                notes.append(f"수집 시도 {idx} 실패: {exc}")
            time.sleep(0.3)

    if not final_html:
        for idx, headers in enumerate(attempts, start=1):
            try:
                req = Request(url, headers=headers)
                with urlopen(req, timeout=12) as resp:
                    raw = resp.read()
                    charset = resp.headers.get_content_charset() or "utf-8"
                    final_html = raw.decode(charset, errors="replace")
                    final_url = url
                    break
            except Exception as exc:
                notes.append(f"보조 수집 시도 {idx} 실패: {exc}")
            time.sleep(0.3)

    if not final_html:
        notes.append("URL 수집 실패로 제한된 평가를 수행했습니다.")
        return "", notes

    # Naver blog often serves a frameset page; fetch the real PostView document.
    frame_match = re.search(
        r'<iframe[^>]+id=["\']mainFrame["\'][^>]+src=["\']([^"\']+)["\']',
        final_html,
        flags=re.IGNORECASE,
    )
    if frame_match and requests is not None:
        frame_src = frame_match.group(1)
        frame_url = urljoin(final_url, frame_src)
        try:
            resp2 = requests.get(
                frame_url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"},
                timeout=12,
                allow_redirects=True,
            )
            if resp2.ok and resp2.text:
                final_html = resp2.text
                final_url = resp2.url
                notes.append("프레임셋 본문(PostView) 페이지를 추가 수집했습니다.")
        except Exception as exc:
            notes.append(f"PostView 추가 수집 실패: {exc}")

    return final_html, notes


def strip_tags(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_images(html_text: str) -> List[Dict[str, object]]:
    images: List[Dict[str, object]] = []
    img_tags = re.findall(r"<img\b[^>]*>", html_text, flags=re.IGNORECASE)
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
    pat = re.compile(rf'{attr}\s*=\s*["\']([^"\']+)["\']', flags=re.IGNORECASE)
    m = pat.search(tag)
    return m.group(1).strip() if m else None


def parse_links_count(html_text: str) -> int:
    hrefs = re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE)
    clean: List[str] = []
    for href in hrefs:
        v = href.strip()
        if not v:
            continue
        low = v.lower()
        if low.startswith("#") or low.startswith("javascript:") or low.startswith("about:blank"):
            continue
        clean.append(v)
    return len(set(clean))


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


def extract_naver_post_body(html_text: str) -> str:
    # Prefer the real post-view block to avoid counting global navigation/sidebar text.
    m = re.search(r'<div id="post-view\d+"', html_text, flags=re.IGNORECASE)
    if m:
        start = m.start()
        se_main = re.search(r'<div[^>]+class="[^"]*se-main-container[^"]*"', html_text[start:], flags=re.IGNORECASE)
        if se_main:
            start = start + se_main.start()
        # post_footer appears after the article body area in Naver PostView pages.
        footer_match = re.search(r'<div[^>]+id="post_footer"', html_text[start:], flags=re.IGNORECASE)
        if footer_match:
            end = start + footer_match.start()
            return html_text[start:end]
        return html_text[start:]
    # Fallback to content area block.
    m2 = re.search(r'<div class="se-main-container"[\s\S]*?</div>\s*</div>', html_text, flags=re.IGNORECASE)
    if m2:
        return m2.group(0)
    return html_text


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def build_token_usage(mode: str, prompt_tokens: int, completion_tokens: int) -> Dict[str, str]:
    total = prompt_tokens + completion_tokens
    return {
        "평가 방식": mode,
        "프롬프트 토큰": str(prompt_tokens),
        "응답 토큰": str(completion_tokens),
        "총 토큰": str(total),
    }


def use_api_evaluator() -> bool:
    # Default is local-only mode to avoid extra API billing.
    return os.environ.get("SALLY_EVAL_MODE", "local").strip().lower() == "api"


def parse_common(html_text: str, source_url: str = "") -> Dict[str, object]:
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
            "video_embedded": False,
            "map_embedded": False,
        }

    is_naver_blog = "blog.naver.com" in source_url or "PostView.naver" in source_url or "blog.naver.com" in html_text
    base_html = extract_naver_post_body(html_text) if is_naver_blog else html_text

    text = strip_tags(base_html)
    images = parse_images(base_html)
    links = parse_links_count(base_html)
    if is_naver_blog:
        images = [
            img
            for img in images
            if any(
                key in str(img.get("src", "")).lower()
                for key in [
                    "postfiles.pstatic.net",
                    "blogfiles.pstatic.net",
                    "blogthumb.pstatic.net",
                    "mblogvideo-phinf.pstatic.net",
                    "phinf.pstatic.net/image.nmv",
                ]
            )
        ]
    hashtags = parse_hashtags(text)
    likes = extract_count(base_html, ["like_count", "likes", "좋아요"])
    comments = extract_count(base_html, ["comment_count", "comments", "댓글"])
    json_ld = extract_json_ld_chunks(base_html)
    video_embedded = bool(
        re.search(
            r"(youtube\.com/embed|player\.vimeo\.com|<video\b|<iframe[^>]+video|v2_video|se-video|_gifmp4|movie_count\":\s*[1-9])",
            base_html,
            flags=re.IGNORECASE,
        )
    )
    map_embedded = bool(
        re.search(
            r"(maps\.google\.com|openstreetmap|kakaomap|naver\.com\/map|<iframe[^>]+map|\"type\":\"v2_map\"|class=\"se-map|static\.map|korea_map\":\s*[1-9]|data-linktype=\"map\")",
            base_html,
            flags=re.IGNORECASE,
        )
    )

    title_match = re.search(r"<title>([\s\S]*?)</title>", html_text, flags=re.IGNORECASE)
    title_tag = html.unescape(title_match.group(1)).strip() if title_match else ""
    title = coalesce(extract_meta(base_html, "og:title"), extract_meta(html_text, "og:title"), title_tag)
    description = coalesce(
        extract_meta(base_html, "og:description"),
        extract_meta(html_text, "og:description"),
        extract_meta(base_html, "description"),
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
        likes = extract_count(base_html, ["edge_media_preview_like", "likeCount", "reaction_count"])
    if comments is None:
        comments = extract_count(base_html, ["edge_media_to_comment", "commentCount"])

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
        "char_count": len(re.sub(r"\s+", "", text)),
        "video_embedded": video_embedded,
        "map_embedded": map_embedded,
    }


def build_dashboard(parsed: Dict[str, object]) -> Dict[str, str]:
    words = int(parsed.get("word_count", 0))
    chars = int(parsed.get("char_count", 0))
    images = len(parsed.get("images", []))
    links = int(parsed.get("links", 0))
    video = bool(parsed.get("video_embedded", False))
    map_data = bool(parsed.get("map_embedded", False))
    return {
        "포함된 텍스트 수": f"{chars}자 / {words}단어",
        "이미지 수": f"{images}",
        "삽입된 링크 수": f"{links}",
        "동영상 삽입 여부": "예" if video else "아니오",
        "지도 데이터 삽입 여부": "예" if map_data else "아니오",
    }


def snippet(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean or "본문 텍스트를 충분히 추출하지 못했습니다."
    return clean[:limit].rstrip() + "..."


def keyword_hits(text: str, words: List[str]) -> int:
    low = text.lower()
    return sum(1 for w in words if w.lower() in low)


def ratio(n: int, d: int) -> float:
    return 0.0 if d <= 0 else n / d


def score_label(score: float) -> str:
    if score >= 4.5:
        return "매우 우수"
    if score >= 3.5:
        return "양호"
    if score >= 2.5:
        return "보통"
    return "개선 필요"


def build_item_review(item: str, score: float, basis: str, action: str = "") -> str:
    diagnosis = {
        "매우 우수": "핵심 지표에서 높은 신뢰도를 보였습니다",
        "양호": "기본 완성도는 충분하지만 더 정교한 보강 여지가 있습니다",
        "보통": "품질이 균일하지 않아 강점과 약점이 함께 관찰됩니다",
        "개선 필요": "현재 데이터 기준으로 보완 우선순위가 높은 상태입니다",
    }
    label = score_label(score)
    core = f"{label} ({score:.1f}/5). {diagnosis[label]}. {basis}"
    if action:
        return f"{core} 개선 제안: {action}"
    return core


def compose_expert_review(
    score: float,
    strengths: List[str],
    weaknesses: List[str],
    feedback: List[str],
) -> str:
    label = score_label(score)
    s = "; ".join(strengths) if strengths else "강점 단서가 제한적입니다."
    w = "; ".join(weaknesses) if weaknesses else "뚜렷한 약점이 관찰되지 않았습니다."
    f = "; ".join(feedback) if feedback else "현 구조를 유지하며 A/B 테스트를 권장합니다."
    return (
        f"{label} ({score:.1f}/5). "
        f"장점: {s} "
        f"단점: {w} "
        f"피드백: {f}"
    )


def infer_audience(text: str, hashtags: List[str]) -> str:
    hobby = keyword_hits(text, ["후기", "리뷰", "맛집", "여행", "카페", "OOTD", "데일리"])
    pro = keyword_hits(text, ["분석", "비교", "가이드", "전략", "인사이트", "트렌드"])
    tags = " ".join([h.lower() for h in hashtags])
    if pro >= 3:
        return "정보 탐색형 독자(비교/검증 중심)"
    if hobby >= 3 or any(k in tags for k in ["daily", "ootd", "travel", "food"]):
        return "라이프스타일 소비자(경험/감성 중심)"
    return "혼합형 독자층(정보+감성 동시 소비)"


def content_maturity(parsed: Dict[str, object]) -> str:
    words = int(parsed.get("word_count", 0))
    images = len(parsed.get("images", []))
    links = int(parsed.get("links", 0))
    if words >= 600 and images >= 4 and links >= 2:
        return "완성도 높은 롱폼 구조"
    if words >= 250 and images >= 2:
        return "표준형 콘텐츠 구조"
    return "경량형 콘텐츠 구조"


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
    audience = infer_audience(text, parsed.get("hashtags", []))
    maturity = content_maturity(parsed)
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
        f"콘텐츠 포지셔닝: {audience}, 포맷 성숙도: {maturity}",
        f"첨부 이미지 요약: {image_types}, 대체텍스트(alt) 포함 {image_with_alt}장, 구조화데이터(JSON-LD) {parsed.get('json_ld_count', 0)}개",
    ]


def build_insta_overview(parsed: Dict[str, object]) -> List[str]:
    text = str(parsed["text"])
    images = parsed["images"]
    hashtags = parsed["hashtags"]
    title = str(parsed.get("title") or "")
    desc = str(parsed.get("description") or "")
    audience = infer_audience(text, hashtags)
    portrait_clues = len(re.findall(r"(portrait|face|selfie|인물|셀카)", text, flags=re.IGNORECASE))
    return [
        f"포스트 핵심 문구: {snippet(coalesce(desc, title, text), 120)}",
        f"타깃 오디언스 추정: {audience}",
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
    sentence_count, avg_len = sentence_stats(text)
    opinion_hits = keyword_hits(text, ["느꼈", "생각", "체감", "개인적", "솔직히"])
    evidence_hits = keyword_hits(text, ["근거", "출처", "통계", "공식", "실험", "비교"])
    cta_hits = keyword_hits(text, ["추천", "구매", "방문", "문의", "신청", "클릭"])
    emotional_hits = keyword_hits(text, ["감동", "만족", "아쉬움", "행복", "놀라", "최고"])

    return {
        BLOG_RUBRIC[0]: compose_expert_review(
            scores[BLOG_RUBRIC[0]],
            strengths=[
                f"이미지 {len(images)}장으로 시각 근거를 제시함" if len(images) > 0 else "이미지 확보가 거의 없음",
                f"alt 텍스트 {sum(1 for i in images if i.get('alt'))}장으로 접근성 단서가 있음" if sum(1 for i in images if i.get("alt")) > 0 else "alt 기반 맥락 설명이 부족함",
            ],
            weaknesses=[
                "피사체/구도별 분류가 약해 메시지 전달력이 떨어질 수 있음" if len(images) < 4 else "이미지 간 역할 분담이 일부 중복됨",
            ],
            feedback=[
                "대표컷-근거컷-결과컷 3단 카드 구성을 고정해 설득력을 높이세요",
                "각 이미지 하단에 맥락 캡션 1문장을 추가하세요",
            ],
        ),
        BLOG_RUBRIC[1]: compose_expert_review(
            scores[BLOG_RUBRIC[1]],
            strengths=[
                f"주관 단서 {opinion_hits}건으로 경험 기반 서사가 존재함" if opinion_hits > 0 else "주관 경험 어조가 약함",
                f"근거 단서 {evidence_hits}건으로 검증 시도가 확인됨" if evidence_hits > 0 else "객관 근거 표현이 희소함",
            ],
            weaknesses=[
                f"근거 링크 {links}개로 외부 검증 연결성이 낮음" if links < 2 else "링크는 있으나 비교축이 명시되지 않음",
            ],
            feedback=[
                "주관 결론 문단 바로 아래에 객관 근거 1개를 반드시 연결하세요",
                "비교 기준(가격/시간/효율)을 문장 내 명시해 판단 기준을 고정하세요",
            ],
        ),
        BLOG_RUBRIC[2]: compose_expert_review(
            scores[BLOG_RUBRIC[2]],
            strengths=[
                f"문장 수 {sentence_count}개로 기본 전개량 확보" if sentence_count > 6 else "문장량이 적어 흐름 완성도가 낮음",
                f"감정 단서 {emotional_hits}건으로 몰입 포인트 존재" if emotional_hits > 0 else "정서적 전환 포인트가 제한적임",
            ],
            weaknesses=[
                f"평균 문장 길이 {avg_len:.1f}자로 리듬 편차가 큼" if avg_len > 80 or avg_len < 18 else "문장 리듬은 비교적 안정적이나 훅이 약함",
            ],
            feedback=[
                "도입(문제)-전개(근거2)-전환(인사이트)-결론(행동)의 4단 템플릿을 반복 적용하세요",
                "첫 3문장 안에 독자 효익 문장을 배치해 이탈을 줄이세요",
            ],
        ),
        BLOG_RUBRIC[3]: compose_expert_review(
            scores[BLOG_RUBRIC[3]],
            strengths=[
                "기본 가독성은 유지됨",
                "문장 단위 정보 전달이 비교적 명확함",
            ],
            weaknesses=[
                "오탈자/공백 오류가 누적되면 전문성 인식이 급격히 하락함",
            ],
            feedback=[
                "발행 전 맞춤법 검사와 소리내어 읽기 검수를 체크리스트화하세요",
                "긴 문장을 2문장으로 분할해 리듬을 확보하세요",
            ],
        ),
        BLOG_RUBRIC[4]: compose_expert_review(
            scores[BLOG_RUBRIC[4]],
            strengths=[
                f"검증 단서(링크 {links}개, JSON-LD {json_ld_count}개)가 일부 존재함" if links + json_ld_count > 0 else "검증 가능한 데이터 노출이 매우 제한적임",
            ],
            weaknesses=[
                f"사실 단어 {evidence_hits}건으로 근거 체인이 약함" if evidence_hits < 3 else "근거는 있으나 출처 표기 형식이 일관되지 않음",
            ],
            feedback=[
                "핵심 주장 3개를 표로 분리하고 출처 URL/발행일/비교기준을 함께 표기하세요",
                "인용 데이터는 최신성 기준(발행일)까지 명시하세요",
            ],
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
    hook_hits = keyword_hits(text_hint, ["new", "첫", "한정", "공개", "단독", "비밀", "드디어"])
    style_hits = keyword_hits(str(parsed.get("text", "")), ["무드", "룩", "톤", "감성", "필름", "시네마"])
    hashtag_density = ratio(len(hashtags), max(1, int(parsed.get("word_count", 1))))

    return {
        INSTAGRAM_RUBRIC[0]: compose_expert_review(
            scores[INSTAGRAM_RUBRIC[0]],
            strengths=[
                f"이미지 {len(images)}장으로 기본 비주얼 세트를 구성함" if len(images) > 0 else "이미지 데이터가 확보되지 않음",
                "피사체 중심 구성 가능성이 확인됨" if len(images) >= 3 else "피사체 시선 유도 정보가 제한됨",
            ],
            weaknesses=[
                "캐러셀 내 역할 분화(훅컷/정보컷/전환컷)가 부족할 가능성",
            ],
            feedback=[
                "첫 컷은 훅, 두 번째 컷은 디테일, 세 번째 컷은 사용 맥락으로 분리하세요",
                "배경 대비를 키워 피사체 분리도를 높이세요",
            ],
        ),
        INSTAGRAM_RUBRIC[1]: compose_expert_review(
            scores[INSTAGRAM_RUBRIC[1]],
            strengths=[
                f"스타일 단서 {style_hits}건으로 콘셉트 의도가 드러남" if style_hits > 0 else "스타일 키워드 단서가 적음",
                f"훅 키워드 {hook_hits}건으로 주목 유도 가능" if hook_hits > 0 else "초반 주목 장치가 약함",
            ],
            weaknesses=[
                "인물 연출 톤(표정/포즈/배경) 일관성이 낮으면 브랜딩이 분산됨",
            ],
            feedback=[
                "한 포스트당 콘셉트 키워드를 1개로 제한해 톤을 고정하세요",
                "인물 컷과 제품 컷의 노출 비율을 7:3으로 실험해 보세요",
            ],
        ),
        INSTAGRAM_RUBRIC[2]: compose_expert_review(
            scores[INSTAGRAM_RUBRIC[2]],
            strengths=[
                f"해시태그 {len(hashtags)}개로 검색 접점을 확보함" if len(hashtags) > 0 else "해시태그 전략이 비어 있음",
            ],
            weaknesses=[
                f"본문 대비 태그 밀도 {hashtag_density:.2f}로 정밀 타깃 세분화가 부족할 수 있음",
            ],
            feedback=[
                "대형/중형/니치 태그를 2/5/3 비율로 계층화하세요",
                "성과 낮은 태그는 2주 단위로 교체해 탐색 효율을 개선하세요",
            ],
        ),
        INSTAGRAM_RUBRIC[3]: compose_expert_review(
            scores[INSTAGRAM_RUBRIC[3]],
            strengths=[
                f"좋아요 {likes if likes is not None else '미확인'}, 댓글 {comments if comments is not None else '미확인'} 데이터로 반응 추세를 확인할 수 있음",
            ],
            weaknesses=[
                "수치가 있어도 저장/공유 유도 문장이 약하면 실제 전환이 낮을 수 있음",
            ],
            feedback=[
                "캡션 말미에 질문형 CTA 1개 + 저장 유도 문장 1개를 고정하세요",
                f"훅 문구('{snippet(text_hint, 40)}')를 첫 문장으로 끌어올려 클릭률을 개선하세요",
            ],
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

    weird_spaces = len(re.findall(r"\s{2,}", text))
    repeated_punct = len(re.findall(r"[!?.,]{3,}", text))
    typo_like = len(re.findall(r"[ㄱ-ㅎㅏ-ㅣ]{3,}", text))

    penalties = weird_spaces * 0.1 + repeated_punct * 0.25 + typo_like * 0.25
    base = 4.6 - min(3.2, penalties)
    return clamp_1_5(base)


def score_blog_factuality(text: str, links: int) -> float:
    if not text:
        return 2.0

    date_hits = len(re.findall(r"20\d{2}[./년-]\s?\d{1,2}", text))
    number_hits = len(re.findall(r"\d+[.,]?\d*", text))
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


def request_sally_ai_review(
    content_type: str,
    url: str,
    parsed: Dict[str, object],
    notes: List[str],
) -> Tuple[Dict[str, float], Dict[str, str], str, Dict[str, str]] | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or requests is None:
        return None

    rubric = BLOG_RUBRIC if content_type == "blog" else INSTAGRAM_RUBRIC
    text = str(parsed.get("text", ""))[:6500]
    payload_for_model = {
        "url": url,
        "type": "네이버 블로그 포스팅" if content_type == "blog" else "인스타그램 피드",
        "title": parsed.get("title", ""),
        "description": parsed.get("description", ""),
        "text_excerpt": text,
        "images_count": len(parsed.get("images", [])),
        "links_count": parsed.get("links", 0),
        "hashtags": parsed.get("hashtags", []),
        "likes": parsed.get("likes"),
        "comments": parsed.get("comments"),
        "video_embedded": parsed.get("video_embedded", False),
        "map_embedded": parsed.get("map_embedded", False),
        "rubric": rubric,
    }
    prompt_json = json.dumps(payload_for_model, ensure_ascii=False)

    system_prompt = (
        "당신은 인플루언서/콘텐츠 전략 전문가 Sally다. "
        "입력된 콘텐츠 증거를 기반으로 각 기준별로 1~5점(0.5 단위) 점수와 상세 심사평을 작성한다. "
        "심사평은 항목마다 서로 다른 근거와 개선안을 제시하고, 비슷한 문장 반복을 피한다. "
        "각 심사평은 반드시 '장점:', '단점:', '피드백:' 3구조를 포함한다. "
        "사람 대신 심사하는 전문 리뷰어의 어조로 작성한다. "
        "반드시 JSON만 출력한다."
    )
    user_prompt = (
        "아래 JSON을 분석해 루브릭별 점수와 심사평을 출력해.\n"
        "출력 형식(JSON):\n"
        "{\n"
        "  \"scores\": {\"<rubric>\": 1.0~5.0},\n"
        "  \"reviews\": {\"<rubric>\": \"상세 심사평\"},\n"
        "  \"summary\": \"전반 평가\"\n"
        "}\n"
        f"입력 데이터: {prompt_json}"
    )

    body = {
        "model": "gpt-4.1-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=40,
        )
        if not resp.ok:
            notes.append(f"Sally AI 평가 호출 실패(HTTP {resp.status_code})")
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed_json = json.loads(content)
        ai_scores: Dict[str, float] = {}
        ai_reviews: Dict[str, str] = {}
        for r in rubric:
            raw_score = parsed_json.get("scores", {}).get(r, 2.5)
            try:
                val = round_half(clamp_1_5(float(raw_score)))
            except Exception:
                val = 2.5
            ai_scores[r] = val

            raw_review = str(parsed_json.get("reviews", {}).get(r, "")).strip()
            ai_reviews[r] = raw_review or "근거 데이터가 제한적이어서 보수적으로 평가했습니다."

        summary = str(parsed_json.get("summary", "")).strip() or "전반 평가 요약을 생성하지 못했습니다."
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", estimate_tokens(system_prompt + user_prompt)))
        completion_tokens = int(usage.get("completion_tokens", estimate_tokens(content)))
        token_usage = build_token_usage("Sally AI 직접 평가", prompt_tokens, completion_tokens)
        return ai_scores, ai_reviews, summary, token_usage
    except Exception as exc:
        notes.append(f"Sally AI 평가 실패: {exc}")
        return None


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
        f"Sally(전문 인플루언서·콘텐츠 전략가) 평가 결과, {tone} "
        f"현재 강점은 '{strongest}'이며, 성장 여지가 가장 큰 축은 '{weakest}'입니다. "
        f"유형: {content_type}"
    )


def evaluate(content_type: str, url: str) -> EvalResult:
    html_text, notes = fetch_html(url)
    parsed = parse_common(html_text, source_url=url)
    dashboard = build_dashboard(parsed)
    ai_result = None
    if use_api_evaluator():
        ai_result = request_sally_ai_review(content_type, url, parsed, notes)

    if content_type == "instagram":
        if ai_result is not None:
            scores, reviews, summary, token_usage = ai_result
            overview = build_insta_overview(parsed)
            avg = round_half(sum(scores.values()) / len(scores))
            return EvalResult("인스타그램 피드", url, scores, reviews, overview, dashboard, token_usage, avg, summary, notes)

        scores = {
            INSTAGRAM_RUBRIC[0]: round_half(score_insta_subject(parsed["images"])),
            INSTAGRAM_RUBRIC[1]: round_half(score_insta_appearance(parsed["text"], parsed["images"])),
            INSTAGRAM_RUBRIC[2]: round_half(score_insta_hashtag_rarity(parsed["hashtags"])),
            INSTAGRAM_RUBRIC[3]: round_half(score_insta_engagement(parsed["likes"], parsed["comments"])),
        }
        reviews = build_insta_reviews(scores, parsed)
        overview = build_insta_overview(parsed)
        avg = round_half(sum(scores.values()) / len(scores))
        summary = build_summary("인스타그램 피드", avg, scores)
        token_usage = build_token_usage("로컬 평가(추가 API 과금 없음)", 0, 0)
        return EvalResult("인스타그램 피드", url, scores, reviews, overview, dashboard, token_usage, avg, summary, notes)

    if ai_result is not None:
        scores, reviews, summary, token_usage = ai_result
        overview = build_blog_overview(parsed)
        avg = round_half(sum(scores.values()) / len(scores))
        return EvalResult("네이버 블로그 포스팅", url, scores, reviews, overview, dashboard, token_usage, avg, summary, notes)

    scores = {
        BLOG_RUBRIC[0]: round_half(score_image_quality(parsed["images"])),
        BLOG_RUBRIC[1]: round_half(score_blog_sincerity_objectivity(parsed["text"], parsed["links"])),
        BLOG_RUBRIC[2]: round_half(score_blog_narrative(parsed["text"])),
        BLOG_RUBRIC[3]: round_half(score_blog_spelling(parsed["text"])),
        BLOG_RUBRIC[4]: round_half(score_blog_factuality(parsed["text"], parsed["links"])),
    }
    reviews = build_blog_reviews(scores, parsed)
    overview = build_blog_overview(parsed)
    avg = round_half(sum(scores.values()) / len(scores))
    summary = build_summary("네이버 블로그 포스팅", avg, scores)
    token_usage = build_token_usage("로컬 평가(추가 API 과금 없음)", 0, 0)
    return EvalResult("네이버 블로그 포스팅", url, scores, reviews, overview, dashboard, token_usage, avg, summary, notes)


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
        dashboard_items = "".join(
            f"<li><strong>{html.escape(k)}:</strong> {html.escape(v)}</li>" for k, v in result.dashboard.items()
        )
        dashboard_block = f"<div class='overview'><h3>포스팅 컨디션 대시보드</h3><ul>{dashboard_items}</ul></div>"
        token_items = "".join(
            f"<li><strong>{html.escape(k)}:</strong> {html.escape(v)}</li>" for k, v in result.token_usage.items()
        )
        token_block = f"<div class='overview'><h3>토큰 사용량</h3><ul>{token_items}</ul></div>"
        notes_block = ""
        if result.notes:
            notes_items = "".join(f"<li>{html.escape(n)}</li>" for n in result.notes)
            notes_block = f"<div class='notes'><h3>참고</h3><ul>{notes_items}</ul></div>"

        result_block = f"""
        <div class='card'>
          <h2>평가 결과</h2>
          <p><strong>유형:</strong> {html.escape(result.content_type)}</p>
          <p><strong>URL:</strong> <a href='{html.escape(result.url)}' target='_blank'>{html.escape(result.url)}</a></p>
          {dashboard_block}
          {token_block}
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
