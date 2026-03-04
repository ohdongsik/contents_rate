from __future__ import annotations

import html

import streamlit as st

from app import evaluate

st.set_page_config(page_title="Sally 콘텐츠 평가기", page_icon="●", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css');

:root {
  --bg: #f1f3f5;
  --panel: #ffffff;
  --ink: #0b0b0b;
  --line: #dadde1;
  --soft: #f7f8fa;
}

html, body, [class*="css"] {
  font-family: 'Manrope', sans-serif;
  color: var(--ink);
}

.stApp {
  background: var(--bg);
}

.block-container {
  max-width: 1160px;
  padding-top: 1.2rem;
  padding-bottom: 3rem;
}

.hero-wrap, .section {
  border: 1px solid var(--line);
  border-radius: 20px;
  background: var(--panel);
  box-shadow: 0 8px 24px rgba(0,0,0,0.05);
}

.hero-wrap {
  padding: 16px;
  margin-bottom: 18px;
}

.top-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 6px 12px 6px;
}

.brand {
  font-weight: 800;
  font-size: 1.18rem;
}

.nav-links {
  display: flex;
  gap: 16px;
  font-size: 0.9rem;
  color: #1b1b1b;
}

.hero {
  min-height: 320px;
  border-radius: 16px;
  padding: 24px;
  display: flex;
  align-items: flex-end;
  background-image:
    linear-gradient(100deg, rgba(255,255,255,0.88) 0%, rgba(255,255,255,0.52) 62%),
    url('https://images.unsplash.com/photo-1473116763249-2faaef81ccda?auto=format&fit=crop&w=1800&q=80');
  background-size: cover;
  background-position: center;
}

.hero h1 {
  margin: 0;
  font-size: 2.95rem;
  line-height: 1.03;
  font-weight: 800;
  letter-spacing: -0.8px;
  color: #050505;
}

.hero p {
  margin-top: 10px;
  color: #111;
  font-size: 1rem;
}

.section {
  margin-top: 16px;
  padding: 20px;
}

.section h2 {
  margin: 0;
  font-size: 1.95rem;
  letter-spacing: -0.4px;
  color: #000;
}

.section-sub {
  margin-top: 6px;
  color: #111;
  font-size: 0.95rem;
}

.value-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0,1fr));
  gap: 12px;
  margin-top: 14px;
}

.value-card, .dash-card, .review-card, .token-card {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--soft);
  padding: 14px;
  color: #000;
}

.icon-bubble {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #eceff3;
  color: #0f0f0f;
  margin-bottom: 8px;
}

.value-title { font-weight: 700; color:#000; }
.value-desc { margin-top:6px; font-size:0.86rem; color:#111; }

.dash-grid { display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 10px; margin-top:12px; }
.dash-k { font-size:0.82rem; color:#111; }
.dash-v { margin-top:5px; font-size:1.2rem; font-weight:800; color:#000; }

.token-grid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; margin-top:12px; }
.token-k { font-size:0.82rem; color:#111; }
.token-v { margin-top:5px; font-size:1.1rem; font-weight:700; color:#000; }

.review-grid { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; margin-top: 12px; }
.review-head { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.review-title { font-weight:700; color:#000; }
.score-pill {
  border: 1px solid #cfd3d8;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 0.82rem;
  font-weight: 700;
  color: #000;
  background: #fff;
}
.review-body { margin-top:10px; line-height:1.58; color:#0d0d0d; font-size:0.95rem; }
.review-body strong { display:inline-block; margin-top:6px; font-size:0.93rem; }

.avg-box, .sum-box {
  margin-top: 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: #fff;
  padding: 13px;
  color: #000;
}
.avg-box { font-weight: 700; }
.sum-title { font-weight: 700; color:#000; }
.sum-body { margin-top: 5px; color:#000; }

ul, li { color: #000 !important; }

@media (max-width: 980px) {
  .value-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .dash-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .token-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .review-grid { grid-template-columns: 1fr; }
  .hero h1 { font-size: 2.2rem; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
<div class="hero-wrap">
  <div class="top-nav">
    <div class="brand">sally*</div>
    <div class="nav-links">
      <span>Professional Review</span>
      <span>Influencer Feed</span>
      <span>Rubric</span>
      <span>Token Usage</span>
    </div>
  </div>
  <div class="hero">
    <div>
      <h1>Modern content<br/>evaluation dashboard</h1>
      <p>등록 URL를 기반으로 Sally가 직접 분석하고, 근거·점수·개선안을 전문가 관점으로 제공합니다.</p>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_values() -> None:
    st.markdown(
        """
<div class="section">
  <h2>Evaluation pillars</h2>
  <p class="section-sub">콘텐츠 전략/카피라이팅/인플루언서 운영 관점의 핵심 축</p>
  <div class="value-grid">
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-camera"></i></div>
      <div class="value-title">Visual Narrative</div>
      <div class="value-desc">이미지의 정보량, 연출 의도, 시선 흐름 분석</div>
    </div>
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-pen"></i></div>
      <div class="value-title">Editorial Quality</div>
      <div class="value-desc">문장 완성도와 전달 구조의 설계력 진단</div>
    </div>
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-list-check"></i></div>
      <div class="value-title">Factual Reliability</div>
      <div class="value-desc">근거 체인과 출처 명확성 점검</div>
    </div>
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-chart-line"></i></div>
      <div class="value-title">Engagement Fit</div>
      <div class="value-desc">반응 구조와 CTA 설계 적합도 평가</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard(result) -> None:
    dash = "".join(
        [
            f"<div class='dash-card'><div class='dash-k'>{html.escape(k)}</div><div class='dash-v'>{html.escape(v)}</div></div>"
            for k, v in result.dashboard.items()
        ]
    )
    st.markdown(
        "<div class='section'><h2>Post Condition Dashboard</h2>"
        "<p class='section-sub'>포스팅 데이터 상태(텍스트/이미지/링크/동영상/지도)를 한눈에 확인합니다.</p>"
        f"<div class='dash-grid'>{dash}</div></div>",
        unsafe_allow_html=True,
    )


def render_token_panel(result) -> None:
    token_cards = "".join(
        [
            f"<div class='token-card'><div class='token-k'>{html.escape(k)}</div><div class='token-v'>{html.escape(v)}</div></div>"
            for k, v in result.token_usage.items()
        ]
    )
    st.markdown(
        "<div class='section'><h2>Token Usage</h2>"
        "<p class='section-sub'>Sally 평가 과정에서 사용된 토큰 지표입니다.</p>"
        f"<div class='token-grid'>{token_cards}</div></div>",
        unsafe_allow_html=True,
    )


def render_reviews(result) -> None:
    overview = "".join([f"<li>{html.escape(x)}</li>" for x in result.overview])
    st.markdown(
        "<div class='section'><h2>Content Intelligence Brief</h2>"
        "<p class='section-sub'>콘텐츠 맥락, 타깃, 구조를 요약한 전략 브리프</p>"
        f"<ul>{overview}</ul></div>",
        unsafe_allow_html=True,
    )

    review_cards = []
    for item, score in result.scores.items():
        review_raw = result.reviews.get(item, "")
        review = format_review_html(review_raw)
        review_cards.append(
            "<div class='review-card'>"
            f"<div class='review-head'><div class='review-title'>{html.escape(item)}</div>"
            f"<div class='score-pill'>★ {score:.1f} / 5</div></div>"
            f"<div class='review-body'>{review}</div>"
            "</div>"
        )

    st.markdown(
        "<div class='section'><h2>Expert Review Panels</h2>"
        "<p class='section-sub'>항목별 근거 중심 심사평</p>"
        f"<div class='review-grid'>{''.join(review_cards)}</div>"
        f"<div class='avg-box'>평균 별점: ★ {result.average:.1f} / 5</div>"
        f"<div class='sum-box'><div class='sum-title'>Overall Verdict</div><div class='sum-body'>{html.escape(result.summary)}</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_notes(result) -> None:
    if result.notes:
        st.markdown("### 참고")
        for note in result.notes:
            st.warning(note)


def format_review_html(text: str) -> str:
    safe = html.escape(text)
    safe = safe.replace(" 장점:", "<br/><strong>장점</strong>: ")
    safe = safe.replace(" 단점:", "<br/><strong>단점</strong>: ")
    safe = safe.replace(" 피드백:", "<br/><strong>피드백</strong>: ")
    safe = safe.replace("; ", "<br/>- ")
    if "<strong>장점</strong>" not in safe and "<strong>단점</strong>" not in safe:
        return safe
    return safe


inject_styles()
render_hero()
render_values()

st.markdown("<div class='section'><h2>Choose your content</h2><p class='section-sub'>URL 기반 분석을 실행하세요.</p></div>", unsafe_allow_html=True)

with st.form("evaluate_form"):
    c1, c2 = st.columns([1, 3])
    with c1:
        content_type_label = st.selectbox("콘텐츠 유형", ["네이버 블로그 포스팅", "인스타그램 피드"])
    with c2:
        url = st.text_input("콘텐츠 URL", placeholder="https://...")
    run = st.form_submit_button("Sally 평가 실행", type="primary")

if run:
    if not url.strip():
        st.error("URL을 입력해 주세요.")
    elif not (url.startswith("http://") or url.startswith("https://")):
        st.error("http:// 또는 https:// URL만 지원합니다.")
    else:
        content_type = "blog" if content_type_label == "네이버 블로그 포스팅" else "instagram"
        with st.spinner("Sally가 콘텐츠를 직접 분석 중입니다..."):
            result = evaluate(content_type, url.strip())

        render_dashboard(result)
        render_token_panel(result)
        render_reviews(result)
        render_notes(result)
