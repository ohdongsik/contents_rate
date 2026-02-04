import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import openai

# 1. 페이지 설정 및 커스텀 스타일
st.set_page_config(page_title="AI 블로그 분석기 Pro", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f9f9fb; }
    .stTextArea textarea { font-size: 14px; }
    .status-card { background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# 2. 본문 추출 로직 (네이버 iframe 대응)
def get_blog_content(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}
    try:
        if "blog.naver.com" in url:
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            ifr = soup.find('iframe', id='mainFrame')
            if ifr:
                real_url = "https://blog.naver.com" + ifr['src']
                res = requests.get(real_url, headers=headers)
                soup = BeautifulSoup(res.text, 'html.parser')
                content = soup.find('div', class_='se-main-container') or soup.find('div', id='postViewArea')
                return content, soup.title.string
        else:
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            return soup.body, soup.title.string
    except:
        return None, None
    return None, None

# 3. AI 분석 함수 (사용자 프롬프트 반영)
def get_ai_evaluation(text, api_key, user_prompt):
    if not api_key:
        return "⚠️ 사이드바에 OpenAI API 키를 입력해주세요."
    
    try:
        client = openai.OpenAI(api_key=api_key)
        # 사용자가 입력한 프롬프트를 시스템 메시지로 전달
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": user_prompt},
                {"role": "user", "content": f"다음 블로그 본문을 분석해라:\n\n{text[:2000]}"}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ AI 분석 중 오류가 발생했습니다: {str(e)}"

# --- UI 레이아웃 ---
st.title("🤖 AI 블로그 분석기 Pro")
st.write("블로그 URL을 입력하고, AI에게 어떤 관점으로 분석할지 직접 명령해 보세요.")

# 사이드바 설정
with st.sidebar:
    st.header("🔑 설정")
    api_key = st.text_input("OpenAI API Key", type="password")
    st.divider()
    st.markdown("### ✍️ AI 분석 프롬프트 설정")
    default_prompt = """You are an AI content quality evaluator.

Your task is to evaluate the quality of images used in a piece of content (such as a blog post, review, or UGC) from an AI-based, objective perspective.

Do NOT judge based on personal taste, aesthetic preference, or emotional beauty.
Instead, evaluate images as information carriers, trust signals, and contextual evidence within the content.

Follow the evaluation framework below.

---

1. Evaluation Principles

- Prioritize information clarity, structural stability, semantic accuracy, and authenticity.
- Avoid subjective aesthetic judgments such as “beautiful” or “artistic.”
- Focus on whether images effectively support the content’s purpose and credibility.
- Penalize excessive use of stock images, reused images, or overly staged visuals.

---

2. Evaluation Categories and Criteria

A. Technical Quality (30 points)
Evaluate whether the image is technically suitable for information delivery.

- Sharpness and resolution (blur, pixelation, noise)
- Exposure and brightness balance (overexposure, crushed shadows)
- Color stability (unnatural color casts, excessive filters)

Deduct points if technical issues interfere with understanding or credibility.

---

B. Structural Quality (25 points)
Evaluate visual structure and composition.

- Clarity of the main subject
- Stability of composition and visual balance
- Framing quality (unintended cropping, distracting background elements)
- Background cleanliness and focus

Deduct points if the main subject is unclear or visually overwhelmed.

---

C. Semantic & Contextual Quality (25 points)
Evaluate meaning and relevance.

- Is the message or subject of the image immediately clear?
- Does the image semantically align with the accompanying text?
- Does the image add explanatory or evidential value rather than decorative value?

Strongly deduct points if the image conflicts with, misrepresents, or adds no value to the text.

---

D. Content & Operational Quality (20 points)
Evaluate authenticity and reuse risk.

- Image originality and duplication risk (stock-like or reused images)
- Authenticity signals (real environment, natural lighting, real usage context)
- Degree of artificial staging or commercial overproduction

Reward images that appear to reflect genuine experience or real-world usage.

---

3. Scoring System

Score each category according to the assigned weights:

- Technical Quality: 30 points
- Structural Quality: 25 points
- Semantic & Contextual Quality: 25 points
- Content & Operational Quality: 20 points

Total score: 100 points

---

4. Output Format

Provide:
1) A score for each category
2) A total score out of 100
3) A short explanation highlighting key strengths and weaknesses
4) A final quality classification:
   - 85–100: High-quality
   - 70–84: Acceptable
   - 50–69: Needs improvement
   - Below 50: Low-quality

---

5. Core Evaluation Philosophy

Images are not decorations.
They are evidence, context carriers, and trust signals.

Evaluate how effectively each image communicates meaning, supports credibility, and fits the content context.
"""
    
    user_custom_prompt = st.text_area(
        "AI에게 내릴 명령어를 수정하세요:",
        value=default_prompt,
        height=300
    )

# 메인 입력창
url_input = st.text_input("분석할 블로그 URL", placeholder="https://blog.naver.com/...")

if st.button("실시간 퀄리티 진단 시작"):
    if not url_input:
        st.error("URL을 입력해 주세요.")
    else:
        with st.spinner('블로그 데이터를 수집하고 AI와 대화 중입니다...'):
            content, title = get_blog_content(url_input)
            
            if content:
                text = content.get_text(separator=' ', strip=True)
                img_count = len(content.find_all('img'))
                char_count = len(text)
                
                # 상단 기본 지표
                st.subheader(f"📌 분석 대상: {title}")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("📸 이미지 수", f"{img_count}개")
                with c2:
                    st.metric("✍️ 글자 수", f"{char_count:,}자")
                with c3:
                    st.metric("🎯 분석 상태", "완료")
                
                # AI 분석 결과
                st.markdown("---")
                st.subheader("📝 AI 전문 진단 리포트")
                result = get_ai_evaluation(text, api_key, user_custom_prompt)
                st.markdown(result)
                
                with st.expander("수집된 본문 텍스트 확인"):
                    st.write(text)
            else:
                st.error("본문 내용을 가져올 수 없습니다. 비공개 글이거나 URL이 올바른지 확인하세요.")
