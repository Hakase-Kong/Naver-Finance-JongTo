import math
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="종목토론방 감성 대시보드",
    page_icon="📈",
    layout="wide",
)

# ------------------------------------------------------------
# 1) Mock data
# 실제 MVP에서는 이 부분을 DB 조회 또는 수집 API 호출로 교체하면 됩니다.
# ------------------------------------------------------------

STOCKS = {
    "005930": {
        "name": "삼성전자",
        "price": "74,200",
        "change": "+1.23%",
        "sentiment_score": 0.42,
        "bullish_ratio": 58,
        "bearish_ratio": 24,
        "neutral_ratio": 18,
        "message_volume": 184,
        "hype_index": 76,
        "updated_at": "오늘 14:35",
        "positive_keywords": {
            "반등": 92,
            "실적": 78,
            "외국인": 65,
            "매수": 61,
            "HBM": 55,
            "저평가": 42,
        },
        "negative_keywords": {
            "횡보": 68,
            "물림": 48,
            "매도": 39,
            "실망": 34,
            "하락": 31,
        },
        "posts": [
            {"title": "외국인 다시 들어오는 분위기네요", "sentiment": "긍정", "views": 482, "likes": 11, "dislikes": 2},
            {"title": "오늘 거래량 보면 단기 반등 가능성 있음", "sentiment": "긍정", "views": 331, "likes": 8, "dislikes": 1},
            {"title": "또 박스권이면 힘들다", "sentiment": "부정", "views": 298, "likes": 4, "dislikes": 7},
            {"title": "실적 발표 전까지는 관망", "sentiment": "중립", "views": 211, "likes": 2, "dislikes": 1},
        ],
    },
    "000660": {
        "name": "SK하이닉스",
        "price": "201,500",
        "change": "+2.04%",
        "sentiment_score": 0.63,
        "bullish_ratio": 67,
        "bearish_ratio": 17,
        "neutral_ratio": 16,
        "message_volume": 236,
        "hype_index": 88,
        "updated_at": "오늘 14:36",
        "positive_keywords": {
            "HBM": 98,
            "AI": 87,
            "신고가": 77,
            "수급": 63,
            "목표가": 58,
            "급등": 45,
        },
        "negative_keywords": {
            "과열": 59,
            "차익": 44,
            "고점": 41,
            "조정": 35,
        },
        "posts": [
            {"title": "HBM 수요 아직 시작도 안 한 듯", "sentiment": "긍정", "views": 692, "likes": 25, "dislikes": 3},
            {"title": "과열은 맞는데 추세가 너무 세다", "sentiment": "긍정", "views": 511, "likes": 14, "dislikes": 5},
            {"title": "고점 매수 조심해야 함", "sentiment": "부정", "views": 403, "likes": 5, "dislikes": 10},
            {"title": "오늘 기관 수급 체크", "sentiment": "중립", "views": 188, "likes": 3, "dislikes": 0},
        ],
    },
    "035420": {
        "name": "NAVER",
        "price": "187,300",
        "change": "-0.74%",
        "sentiment_score": -0.18,
        "bullish_ratio": 31,
        "bearish_ratio": 46,
        "neutral_ratio": 23,
        "message_volume": 97,
        "hype_index": 42,
        "updated_at": "오늘 14:33",
        "positive_keywords": {
            "저점": 57,
            "반등": 43,
            "검색": 31,
            "웹툰": 25,
        },
        "negative_keywords": {
            "부진": 72,
            "하락": 69,
            "매물": 47,
            "실망": 45,
            "손절": 34,
        },
        "posts": [
            {"title": "반등 타이밍 아직 아닌 듯", "sentiment": "부정", "views": 230, "likes": 3, "dislikes": 6},
            {"title": "웹툰 쪽 기대감은 남아있음", "sentiment": "긍정", "views": 144, "likes": 5, "dislikes": 1},
            {"title": "계속 매물 나오는 게 문제", "sentiment": "부정", "views": 201, "likes": 4, "dislikes": 8},
            {"title": "오늘은 그냥 관망", "sentiment": "중립", "views": 93, "likes": 1, "dislikes": 0},
        ],
    },
}

# ------------------------------------------------------------
# 2) Utility functions
# ------------------------------------------------------------

def get_sentiment_label(score: float) -> str:
    if score >= 0.35:
        return "긍정 우세"
    if score <= -0.2:
        return "부정 우세"
    return "중립"


def keyword_dataframe(keyword_dict: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"keyword": key, "weight": value} for key, value in keyword_dict.items()]
    ).sort_values("weight", ascending=False)


def render_keyword_chips(keyword_dict: dict[str, int]) -> None:
    if not keyword_dict:
        st.caption("키워드가 없습니다.")
        return

    max_weight = max(keyword_dict.values())
    html = "<div style='display:flex;flex-wrap:wrap;gap:8px;'>"
    for word, weight in sorted(keyword_dict.items(), key=lambda x: x[1], reverse=True):
        size = 13 + math.floor((weight / max_weight) * 9)
        html += (
            f"<span style='font-size:{size}px;"
            "background:#f1f5f9;"
            "padding:7px 11px;"
            "border-radius:999px;"
            "font-weight:700;"
            "color:#334155;'>"
            f"#{word}"
            "</span>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def find_stock(query: str) -> tuple[str, dict]:
    normalized = query.strip().lower()
    for code, stock in STOCKS.items():
        if normalized in code.lower() or normalized in stock["name"].lower():
            return code, stock
    return "005930", STOCKS["005930"]


# ------------------------------------------------------------
# 3) Sidebar
# ------------------------------------------------------------

with st.sidebar:
    st.header("📌 데모 설정")

    stock_options = [f"{code} · {data['name']}" for code, data in STOCKS.items()]
    selected_option = st.selectbox("샘플 종목", stock_options)
    selected_code = selected_option.split(" · ")[0]

    search_query = st.text_input(
        "종목명 또는 코드 검색",
        value=selected_code,
        placeholder="예: 삼성전자 또는 005930",
    )

    st.divider()
    st.caption("현재 버전은 mock 데이터 기반입니다.")
    st.caption("실서비스에서는 수집기 → DB → 감성분석 API → Streamlit 화면 순서로 연결합니다.")

# ------------------------------------------------------------
# 4) Main layout
# ------------------------------------------------------------

code, stock = find_stock(search_query)

st.title("📈 종목토론방 실시간 여론 대시보드")
st.caption("네이버 종목토론방의 최신 게시글 제목을 기반으로 오늘의 커뮤니티 감성지수와 과열도를 추정합니다.")

header_left, header_right = st.columns([2, 1])

with header_left:
    st.subheader(f"{stock['name']} · {code}")
    st.write(f"현재가 **{stock['price']}원** · 등락률 **{stock['change']}** · 업데이트 **{stock['updated_at']}**")

with header_right:
    label = get_sentiment_label(stock["sentiment_score"])
    st.metric(
        label="오늘의 감성 상태",
        value=label,
        delta=f"감성 점수 {stock['sentiment_score']:+.2f}",
    )

st.divider()

metric_cols = st.columns(4)
metric_cols[0].metric("긍정 비율", f"{stock['bullish_ratio']}%", f"부정 {stock['bearish_ratio']}%")
metric_cols[1].metric("게시글 수", f"{stock['message_volume']:,}", "오늘 수집 기준")
metric_cols[2].metric("과열도", f"{stock['hype_index']}", "글 수·조회수·추천수")
metric_cols[3].metric("감성 점수", f"{stock['sentiment_score']:+.2f}", "-1 ~ +1")

# ------------------------------------------------------------
# 5) Charts
# ------------------------------------------------------------

chart_col_1, chart_col_2 = st.columns([1, 1])

with chart_col_1:
    st.subheader("감성 비율")
    ratio_df = pd.DataFrame(
        {
            "sentiment": ["긍정", "부정", "중립"],
            "ratio": [
                stock["bullish_ratio"],
                stock["bearish_ratio"],
                stock["neutral_ratio"],
            ],
        }
    )
    st.bar_chart(ratio_df, x="sentiment", y="ratio")

with chart_col_2:
    st.subheader("키워드 가중치")
    positive_df = keyword_dataframe(stock["positive_keywords"])
    negative_df = keyword_dataframe(stock["negative_keywords"])

    keyword_df = pd.concat(
        [
            positive_df.assign(type="긍정"),
            negative_df.assign(type="부정"),
        ],
        ignore_index=True,
    )
    st.dataframe(keyword_df, use_container_width=True, hide_index=True)

# ------------------------------------------------------------
# 6) Keyword cloud and posts
# ------------------------------------------------------------

keyword_col_1, keyword_col_2 = st.columns(2)

with keyword_col_1:
    st.subheader("👍 긍정 키워드")
    render_keyword_chips(stock["positive_keywords"])

with keyword_col_2:
    st.subheader("👎 부정 키워드")
    render_keyword_chips(stock["negative_keywords"])

st.divider()

st.subheader("최근 대표 글 제목")
posts_df = pd.DataFrame(stock["posts"])
st.dataframe(
    posts_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "title": "제목",
        "sentiment": "감성",
        "views": "조회",
        "likes": "추천",
        "dislikes": "비추천",
    },
)

st.warning(
    "본 지표는 네이버 종목토론방 게시글 기반의 비정형 커뮤니티 감성 분석 결과이며, "
    "투자 권유나 매매 신호가 아닙니다."
)

# ------------------------------------------------------------
# 7) Backend connection guide
# ------------------------------------------------------------

with st.expander("백엔드 연결 구조 보기"):
    st.code(
        """
project/
  app.py                         # Streamlit 화면
  collector/naver_board.py        # 네이버 종목토론방 첫 페이지 수집기
  sentiment/rule_model.py         # 룰 기반 감성분석
  storage/db.py                   # SQLite/Postgres 저장
  data/posts.db                   # 수집 데이터

데이터 흐름:
1. collector가 종목별 첫 페이지 최신 글 수집
2. post_id 또는 URL 기준 중복 제거
3. title 텍스트로 감성분석 수행
4. 일자·종목별 지표 집계
5. Streamlit에서 집계 결과 시각화
        """,
        language="text",
    )

st.caption(f"마지막 화면 렌더링: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
