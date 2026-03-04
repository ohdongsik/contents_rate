from __future__ import annotations

import html

import streamlit as st

from app import evaluate

st.set_page_config(page_title="Sally 콘텐츠 평가기", page_icon="★", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css');

:root {
  --bg: #eef2f4;
  --paper: #ffffff;
  --ink: #1d2428;
  --muted: #5b676f;
  --line: #d6dde2;
  --accent: #1a8b64;
  --accent-2: #2e5f8a;
  --soft: #f6f8fa;
}

html, body, [class*="css"] {
  font-family: 'Outfit', sans-serif;
}

.stApp {
  background: radial-gradient(1200px 420px at 75% -10%, #d4ebe2 0%, var(--bg) 55%);
}

.block-container {
  max-width: 1160px;
  padding-top: 1.2rem;
  padding-bottom: 3rem;
}

.hero-wrap {
  border: 1px solid var(--line);
  border-radius: 22px;
  background: var(--paper);
  padding: 16px;
  box-shadow: 0 10px 35px rgba(18, 35, 48, 0.08);
  margin-bottom: 26px;
}

.top-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 8px 12px 8px;
  color: var(--ink);
}

.brand {
  font-weight: 800;
  letter-spacing: 0.2px;
  font-size: 1.2rem;
}

.nav-links {
  display: flex;
  gap: 18px;
  color: var(--muted);
  font-weight: 500;
  font-size: 0.9rem;
}

.hero {
  min-height: 340px;
  border-radius: 18px;
  overflow: hidden;
  padding: 26px;
  display: flex;
  align-items: flex-end;
  background-image:
    linear-gradient(100deg, rgba(20, 30, 40, 0.65) 0%, rgba(20, 30, 40, 0.15) 62%),
    url('https://images.unsplash.com/photo-1473116763249-2faaef81ccda?auto=format&fit=crop&w=1800&q=80');
  background-size: cover;
  background-position: center;
}

.hero h1 {
  margin: 0;
  color: #f6f8f9;
  font-size: 3.1rem;
  line-height: 1.03;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.hero p {
  margin: 10px 0 0 0;
  color: #dde5ea;
  font-size: 1.02rem;
}

.section {
  margin-top: 18px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--paper);
  box-shadow: 0 8px 30px rgba(20, 30, 40, 0.05);
  padding: 20px;
}

.section h2 {
  margin: 0;
  font-size: 2rem;
  letter-spacing: -0.4px;
}

.section-sub {
  margin: 6px 0 0 0;
  color: var(--muted);
}

.value-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.value-card {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px;
  background: var(--soft);
}

.icon-bubble {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e6edf2;
  color: var(--accent-2);
  margin-bottom: 8px;
}

.value-title {
  font-weight: 700;
  font-size: 0.95rem;
}

.value-desc {
  color: var(--muted);
  font-size: 0.85rem;
  margin-top: 5px;
}

.dash-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.dash-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f7fafc;
  padding: 12px;
}

.dash-k {
  font-size: 0.82rem;
  color: var(--muted);
}

.dash-v {
  margin-top: 6px;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--ink);
}

.review-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.review-card {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px;
  background: #fcfdff;
}

.review-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.review-title {
  font-weight: 700;
  font-size: 1rem;
}

.score-pill {
  border-radius: 999px;
  border: 1px solid #c4d4de;
  background: #eef5f9;
  padding: 4px 10px;
  font-size: 0.82rem;
  font-weight: 700;
  color: #23465f;
  white-space: nowrap;
}

.review-body {
  margin-top: 10px;
  color: #33414b;
  line-height: 1.55;
  font-size: 0.95rem;
}

.sum-box {
  margin-top: 12px;
  border: 1px solid #b8d5c8;
  border-radius: 12px;
  background: #edf8f3;
  padding: 14px;
}

.sum-title {
  font-weight: 700;
  color: #1d5a42;
}

.sum-body {
  margin-top: 6px;
  color: #25463a;
}

.avg-box {
  margin-top: 12px;
  border-radius: 12px;
  background: linear-gradient(120deg, #1a8b64, #2b6d9b);
  color: #fff;
  padding: 14px;
  font-size: 1.05rem;
  font-weight: 600;
}

@media (max-width: 980px) {
  .value-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .review-grid { grid-template-columns: 1fr; }
  .dash-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero h1 { font-size: 2.3rem; }
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
      <span>Blog Review</span>
      <span>Influencer Feed</span>
      <span>Insight</span>
      <span>Rubric</span>
    </div>
  </div>
  <div class="hero">
    <div>
      <h1>Evaluate with<br/>professional depth</h1>
      <p>콘텐츠 전략가 관점으로 포스팅의 품질, 설득력, 반응 잠재력을 진단합니다.</p>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_value_section() -> None:
    st.markdown(
        """
<div class="section">
  <h2>Top values for your content</h2>
  <p class="section-sub">디자인·스토리·신뢰·반응의 4축으로 Sally 평가 기준을 운영합니다.</p>
  <div class="value-grid">
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-image"></i></div>
      <div class="value-title">Visual Quality</div>
      <div class="value-desc">이미지 구성, 시선 유도, 정보 전달력 중심 평가</div>
    </div>
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-pen-nib"></i></div>
      <div class="value-title">Narrative Craft</div>
      <div class="value-desc">도입-전개-결론의 리듬과 설득 구조 분석</div>
    </div>
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-shield"></i></div>
      <div class="value-title">Factual Trust</div>
      <div class="value-desc">근거 추적 가능성과 정보 신뢰도 확인</div>
    </div>
    <div class="value-card">
      <div class="icon-bubble"><i class="fa-solid fa-bolt"></i></div>
      <div class="value-title">Engagement Fit</div>
      <div class="value-desc">반응 지표와 CTA 구조의 정합성 진단</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard(result) -> None:
    cards = []
    for key, value in result.dashboard.items():
        cards.append(
            f"<div class='dash-card'><div class='dash-k'>{html.escape(key)}</div><div class='dash-v'>{html.escape(value)}</div></div>"
        )
    st.markdown(
        "<div class='section'><h2>Post Condition Dashboard</h2>"
        "<p class='section-sub'>포스팅의 기본 체력을 구성하는 핵심 데이터 요약입니다.</p>"
        f"<div class='dash-grid'>{''.join(cards)}</div></div>",
        unsafe_allow_html=True,
    )


def render_reviews(result) -> None:
    overview = "".join([f"<li>{html.escape(x)}</li>" for x in result.overview])
    st.markdown(
        "<div class='section'>"
        "<h2>Content Intelligence Brief</h2>"
        "<p class='section-sub'>콘텐츠의 맥락과 포지셔닝을 요약한 전문가 브리프입니다.</p>"
        f"<ul>{overview}</ul>"
        "</div>",
        unsafe_allow_html=True,
    )

    review_cards = []
    for item, score in result.scores.items():
        review = result.reviews.get(item, "")
        review_cards.append(
            "<div class='review-card'>"
            f"<div class='review-head'><div class='review-title'>{html.escape(item)}</div>"
            f"<div class='score-pill'>★ {score:.1f} / 5</div></div>"
            f"<div class='review-body'>{html.escape(review)}</div>"
            "</div>"
        )

    st.markdown(
        "<div class='section'>"
        "<h2>Expert Review Panels</h2>"
        "<p class='section-sub'>각 항목별로 관찰·해석·개선제안을 분리해 제시합니다.</p>"
        f"<div class='review-grid'>{''.join(review_cards)}</div>"
        f"<div class='avg-box'>평균 별점: ★ {result.average:.1f} / 5</div>"
        f"<div class='sum-box'><div class='sum-title'>Overall Editorial Verdict</div>"
        f"<div class='sum-body'>{html.escape(result.summary)}</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_notes(result) -> None:
    if result.notes:
        st.markdown("### 참고")
        for note in result.notes:
            st.warning(note)


inject_styles()
render_hero()
render_value_section()

st.markdown("<div class='section'><h2>Choose your content</h2><p class='section-sub'>URL을 입력하고 전문가형 평가를 실행하세요.</p></div>", unsafe_allow_html=True)

with st.form("evaluate_form"):
    c1, c2 = st.columns([1, 3])
    with c1:
        content_type_label = st.selectbox(
            "콘텐츠 유형",
            options=["네이버 블로그 포스팅", "인스타그램 피드"],
        )
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
        with st.spinner("콘텐츠를 분석하고 있습니다..."):
            result = evaluate(content_type, url.strip())

        render_dashboard(result)
        render_reviews(result)
        render_notes(result)
