# Sally 콘텐츠 별점 평가 웹앱

URL을 입력하면 `Sally`가 동일한 루브릭으로 콘텐츠를 평가하고,
항목별 별점(1~5), 평균 별점, 전반 평가 코멘트를 보여줍니다.

## 지원 콘텐츠
- 네이버 블로그 포스팅
- 인스타그램 피드

## 로컬 실행 방법 (Streamlit)
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

브라우저에서 Streamlit이 출력한 주소로 접속합니다.

## Streamlit Cloud 배포
1. Streamlit 계정에서 `New app` 클릭
2. Repository: `ohdongsik/contents_rate`
3. Branch: `main`
4. Main file path: `streamlit_app.py`
5. `Deploy` 실행

## 평가 기준
### 1) 블로그 포스팅
- 이미지 퀄리티
- 진정성/객관성
- 내러티브
- 맞춤법/표기
- 정보 사실성

### 2) 인스타그램 피드
- 피사체 퀄리티
- 인물 표현 점수
- 해시태그 희소성
- 좋아요/댓글 반응

## 구현 방식
- Streamlit UI + 파이썬 평가 엔진
- URL HTML을 수집한 뒤 텍스트/이미지/해시태그/반응값(수집 가능 시) 파싱
- 항목별 휴리스틱 점수(1~5) 계산 후 평균 별점 산출
- 평균 구간에 따라 Sally 총평 자동 생성

## 참고
- 인스타그램/일부 사이트는 봇 차단 정책 때문에 데이터 수집이 제한될 수 있습니다.
- 이 경우 앱은 중립 점수 기반으로 결과를 보여주며, 화면의 `참고` 영역에 안내 메시지를 표시합니다.
