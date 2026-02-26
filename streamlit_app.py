from __future__ import annotations

import streamlit as st

from app import evaluate

st.set_page_config(page_title="Sally 콘텐츠 평가기", page_icon="⭐", layout="centered")

st.title("Sally 콘텐츠 평가기")
st.caption("URL을 입력하면 동일한 루브릭으로 항목별 별점(1~5), 심사평, 평균 별점을 계산합니다.")

content_type_label = st.selectbox(
    "콘텐츠 유형",
    options=["네이버 블로그 포스팅", "인스타그램 피드"],
)
url = st.text_input("콘텐츠 URL", placeholder="https://...")

run = st.button("Sally 평가 실행", type="primary")

if run:
    if not url.strip():
        st.error("URL을 입력해 주세요.")
    elif not (url.startswith("http://") or url.startswith("https://")):
        st.error("http:// 또는 https:// URL만 지원합니다.")
    else:
        content_type = "blog" if content_type_label == "네이버 블로그 포스팅" else "instagram"

        with st.spinner("콘텐츠를 분석하고 있습니다..."):
            result = evaluate(content_type, url.strip())

        st.subheader("평가 결과")
        st.write(f"**유형:** {result.content_type}")
        st.write(f"**URL:** {result.url}")

        st.markdown("### 콘텐츠 요약정보")
        for item in result.overview:
            st.markdown(f"- {item}")

        st.markdown("### 항목별 별점 및 심사평")
        for item, score in result.scores.items():
            st.markdown(f"**{item}**: {score:.1f} / 5")
            review = result.reviews.get(item, "")
            if review:
                st.caption(review)

        st.markdown(f"### 평균 별점: **{result.average:.1f} / 5**")
        st.info(result.summary)

        if result.notes:
            st.markdown("### 참고")
            for note in result.notes:
                st.warning(note)
