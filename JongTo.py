import math
import re
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="종목토론방 감성 대시보드",
    page_icon="📈",
    layout="wide",
)

# ------------------------------------------------------------
# 1) 기본 설정
# ------------------------------------------------------------

NAVER_BOARD_URL = "https://finance.naver.com/item/board.naver"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

STOCK_PRESETS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "005380": "현대차",
    "051910": "LG화학",
    "035720": "카카오",
    "068270": "셀트리온",
    "373220": "LG에너지솔루션",
}

POSITIVE_WORDS = [
    "상한가", "급등", "간다", "가즈아", "매수", "호재", "돌파", "신고가", "반등", "대박",
    "상승", "불장", "기대", "저평가", "수급", "실적", "목표가", "외국인", "기관", "강세",
    "랠리", "회복", "성장", "수혜", "흑자", "계약", "수주", "좋다", "버틴다", "추세",
    "날아", "올라", "오른다", "매집", "추매", "바닥", "턴어라운드", "기회", "상방",
]

NEGATIVE_WORDS = [
    "폭락", "하락", "손절", "물렸다", "물림", "악재", "끝났다", "망했다", "팔아라", "개미지옥",
    "떡락", "하방", "실망", "폭망", "고점", "과열", "조정", "매도", "부진", "적자",
    "리스크", "불안", "급락", "던져", "털림", "횡보", "매물", "약세", "위험", "거품",
    "물타기", "물렸", "빠진다", "내린다", "손실", "시체", "나락", "답없", "망함",
]

MOCK_STOCKS = {
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
            {
                "title": "외국인 다시 들어오는 분위기네요",
                "sentiment": "긍정",
                "views": 482,
                "likes": 11,
                "dislikes": 2,
                "date": "-",
                "url": "",
            },
            {
                "title": "오늘 거래량 보면 단기 반등 가능성 있음",
                "sentiment": "긍정",
                "views": 331,
                "likes": 8,
                "dislikes": 1,
                "date": "-",
                "url": "",
            },
            {
                "title": "또 박스권이면 힘들다",
                "sentiment": "부정",
                "views": 298,
                "likes": 4,
                "dislikes": 7,
                "date": "-",
                "url": "",
            },
            {
                "title": "실적 발표 전까지는 관망",
                "sentiment": "중립",
                "views": 211,
                "likes": 2,
                "dislikes": 1,
                "date": "-",
                "url": "",
            },
        ],
    }
}

# ------------------------------------------------------------
# 2) 네이버 종목토론방 수집
# ------------------------------------------------------------

def to_int(value: Any) -> int:
    text = str(value).replace(",", "").strip()
    return int(text) if text.isdigit() else 0


def decode_naver_html(content: bytes) -> str:
    """
    네이버 금융은 cp949/euc-kr 계열 인코딩을 쓰는 경우가 많습니다.
    Render 환경에서 response.text에 맡기면 한글이 깨질 수 있어 직접 디코딩합니다.
    """
    for encoding in ["cp949", "euc-kr", "utf-8"]:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue

    return content.decode("cp949", errors="replace")


def clean_title(title: str) -> str:
    title = str(title)
    title = title.replace("\xa0", " ")
    title = title.replace("답글", "")
    title = re.sub(r"\s+", " ", title).strip()
    return title


@st.cache_data(ttl=180, show_spinner=False)
def fetch_naver_board_first_page(stock_code: str) -> pd.DataFrame:
    """네이버 종목토론방 첫 페이지의 최신 글 목록만 수집합니다."""
    response = requests.get(
        NAVER_BOARD_URL,
        params={"code": stock_code},
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()

    html = decode_naver_html(response.content)
    soup = BeautifulSoup(html, "html.parser")

    rows: list[dict[str, Any]] = []

    for tr in soup.select("table.type2 tr"):
        tds = tr.select("td")
        if len(tds) < 6:
            continue

        cols = [td.get_text(" ", strip=True) for td in tds]
        date_text = cols[0]

        # 실제 게시글 행만 통과시킵니다. 예: 2026.05.27 14:35
        if not re.match(r"^\d{4}\.\d{2}\.\d{2}", date_text):
            continue

        link_tag = tr.select_one("a")

        # 제목은 td 전체 텍스트보다 a 태그 텍스트를 우선 사용합니다.
        # 그래야 아이콘, 답글 표시, 여분 텍스트가 덜 섞입니다.
        if link_tag:
            title = link_tag.get_text(" ", strip=True)
        else:
            title = cols[1]

        title = clean_title(title)
        if not title:
            continue

        author = cols[2] if len(cols) > 2 else ""
        views = cols[3] if len(cols) > 3 else "0"
        likes = cols[4] if len(cols) > 4 else "0"
        dislikes = cols[5] if len(cols) > 5 else "0"

        post_url = ""
        if link_tag and link_tag.get("href"):
            post_url = "https://finance.naver.com" + link_tag["href"]

        rows.append(
            {
                "date": date_text,
                "title": title,
                "author": author,
                "views": to_int(views),
                "likes": to_int(likes),
                "dislikes": to_int(dislikes),
                "url": post_url,
            }
        )

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# 3) 감성 분석 및 지표 집계
# ------------------------------------------------------------

def classify_sentiment(text: str) -> str:
    text = str(text)

    positive_hits = sum(1 for word in POSITIVE_WORDS if word in text)
    negative_hits = sum(1 for word in NEGATIVE_WORDS if word in text)

    if positive_hits > negative_hits:
        return "긍정"
    if negative_hits > positive_hits:
        return "부정"
    return "중립"


def sentiment_to_score(label: str) -> int:
    if label == "긍정":
        return 1
    if label == "부정":
        return -1
    return 0


def extract_keywords(
    posts_df: pd.DataFrame,
    sentiment_label: str,
    vocabulary: list[str],
) -> dict[str, int]:
    if posts_df.empty:
        return {}

    filtered = posts_df[posts_df["sentiment"] == sentiment_label]
    if filtered.empty:
        return {}

    result: dict[str, int] = {}

    for word in vocabulary:
        mask = filtered["title"].astype(str).str.contains(re.escape(word), regex=True)
        count = int(mask.sum())

        if count > 0:
            matched_views = filtered[mask]["views"].sum()
            result[word] = int(count * 20 + math.log1p(matched_views) * 10)

    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:10])


def build_stock_summary(
    stock_code: str,
    stock_name: str,
    posts_df: pd.DataFrame,
) -> dict[str, Any]:
    if posts_df.empty:
        raise ValueError("수집된 게시글이 없습니다.")

    df = posts_df.copy()

    df["sentiment"] = df["title"].apply(classify_sentiment)
    df["sentiment_value"] = df["sentiment"].apply(sentiment_to_score)

    df["weight"] = (
        1
        + df["views"].fillna(0).apply(lambda x: math.log1p(max(x, 0)))
        + df["likes"].fillna(0) * 0.15
        - df["dislikes"].fillna(0) * 0.08
    ).clip(lower=0.2)

    total_weight = df["weight"].sum()
    if total_weight == 0:
        sentiment_score = 0.0
    else:
        sentiment_score = float(
            (df["sentiment_value"] * df["weight"]).sum() / total_weight
        )

    message_volume = len(df)
    bullish_ratio = round((df["sentiment"] == "긍정").mean() * 100)
    bearish_ratio = round((df["sentiment"] == "부정").mean() * 100)
    neutral_ratio = 100 - bullish_ratio - bearish_ratio

    avg_views = df["views"].mean() if message_volume else 0
    total_engagement = df["likes"].sum() + df["dislikes"].sum()

    hype_index = min(
        100,
        round(
            message_volume * 3
            + math.log1p(avg_views) * 8
            + total_engagement * 0.4
        ),
    )

    posts = df[
        ["title", "sentiment", "views", "likes", "dislikes", "date", "url"]
    ].head(20).to_dict("records")

    return {
        "name": stock_name,
        "price": "-",
        "change": "-",
        "sentiment_score": sentiment_score,
        "bullish_ratio": bullish_ratio,
        "bearish_ratio": bearish_ratio,
        "neutral_ratio": neutral_ratio,
        "message_volume": message_volume,
        "hype_index": hype_index,
        "updated_at": datetime.now().strftime("%H:%M"),
        "positive_keywords": extract_keywords(df, "긍정", POSITIVE_WORDS),
        "negative_keywords": extract_keywords(df, "부정", NEGATIVE_WORDS),
        "posts": posts,
        "raw_posts_df": df,
    }


def get_sentiment_label(score: float) -> str:
    if score >= 0.35:
        return "긍정 우세"
    if score <= -0.2:
        return "부정 우세"
    return "중립"


def keyword_dataframe(keyword_dict: dict[str, int]) -> pd.DataFrame:
    if not keyword_dict:
        return pd.DataFrame(columns=["keyword", "weight"])

    return pd.DataFrame(
        [{"keyword": key, "weight": value} for key, value in keyword_dict.items()]
    ).sort_values("weight", ascending=False)


def render_keyword_chips(keyword_dict: dict[str, int]) -> None:
    if not keyword_dict:
        st.caption("해당 감성 키워드가 아직 충분히 감지되지 않았습니다.")
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


def find_stock_name(stock_code: str) -> str:
    return STOCK_PRESETS.get(stock_code, f"종목 {stock_code}")


# ------------------------------------------------------------
# 4) Sidebar
# ------------------------------------------------------------

with st.sidebar:
    st.header("📌 데이터 설정")

    stock_options = [f"{code} · {name}" for code, name in STOCK_PRESETS.items()]
    selected_option = st.selectbox("종목 선택", stock_options)
    selected_code = selected_option.split(" · ")[0]

    stock_code = st.text_input(
        "종목코드 직접 입력",
        value=selected_code,
        placeholder="예: 005930",
        max_chars=6,
    )

    use_live_data = st.toggle("실제 네이버 데이터 수집", value=True)

    if st.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("첫 페이지 최신 글만 수집합니다.")
    st.caption("수집 실패 시 mock 데이터로 자동 전환됩니다.")

# ------------------------------------------------------------
# 5) Data loading
# ------------------------------------------------------------

stock_code = re.sub(r"\D", "", stock_code)[:6] or "005930"
stock_name = find_stock_name(stock_code)

data_source = "mock"
load_error = None

if use_live_data:
    try:
        live_posts_df = fetch_naver_board_first_page(stock_code)
        stock = build_stock_summary(stock_code, stock_name, live_posts_df)
        data_source = "live"
    except Exception as exc:
        load_error = str(exc)
        stock = MOCK_STOCKS.get("005930")
else:
    stock = MOCK_STOCKS.get(stock_code, MOCK_STOCKS["005930"])

# ------------------------------------------------------------
# 6) Main layout
# ------------------------------------------------------------

st.title("📈 종목토론방 실시간 여론 대시보드")
st.caption(
    "네이버 종목토론방의 최신 게시글 제목을 기반으로 "
    "오늘의 커뮤니티 감성지수와 과열도를 추정합니다."
)

if data_source == "live":
    st.success("실제 네이버 종목토론방 첫 페이지 데이터를 수집해 표시 중입니다.")
elif load_error:
    st.warning(f"실제 데이터 수집에 실패해 mock 데이터로 표시합니다. 오류: {load_error}")
else:
    st.info("mock 데이터로 표시 중입니다.")

header_left, header_right = st.columns([2, 1])

with header_left:
    st.subheader(f"{stock['name']} · {stock_code}")
    st.write(
        f"현재가 **{stock['price']}원** · "
        f"등락률 **{stock['change']}** · "
        f"업데이트 **{stock['updated_at']}**"
    )

with header_right:
    label = get_sentiment_label(stock["sentiment_score"])
    st.metric(
        label="오늘의 감성 상태",
        value=label,
        delta=f"감성 점수 {stock['sentiment_score']:+.2f}",
    )

st.divider()

metric_cols = st.columns(4)

metric_cols[0].metric(
    "긍정 비율",
    f"{stock['bullish_ratio']}%",
    f"부정 {stock['bearish_ratio']}%",
)

metric_cols[1].metric(
    "게시글 수",
    f"{stock['message_volume']:,}",
    "첫 페이지 기준",
)

metric_cols[2].metric(
    "과열도",
    f"{stock['hype_index']}",
    "글 수·조회수·추천수",
)

metric_cols[3].metric(
    "감성 점수",
    f"{stock['sentiment_score']:+.2f}",
    "-1 ~ +1",
)

# ------------------------------------------------------------
# 7) Charts
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
# 8) Keyword cloud and posts
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

if "url" in posts_df.columns:
    display_posts_df = posts_df.drop(columns=["url"])
else:
    display_posts_df = posts_df

st.dataframe(
    display_posts_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "title": "제목",
        "sentiment": "감성",
        "views": "조회",
        "likes": "추천",
        "dislikes": "비추천",
        "date": "작성일시",
    },
)

if data_source == "live" and not posts_df.empty and "url" in posts_df.columns:
    with st.expander("게시글 링크 보기"):
        for _, row in posts_df.head(10).iterrows():
            if row.get("url"):
                st.markdown(f"- [{row['title']}]({row['url']})")

st.warning(
    "본 지표는 네이버 종목토론방 게시글 기반의 비정형 커뮤니티 감성 분석 결과이며, "
    "투자 권유나 매매 신호가 아닙니다."
)

# ------------------------------------------------------------
# 9) Backend connection guide
# ------------------------------------------------------------

with st.expander("현재 MVP 구조 보기"):
    st.code(
        """
현재 버전:
1. Streamlit app.py 실행
2. 네이버 종목토론방 첫 페이지 최신 글 수집
3. 제목 기반 룰 감성분석
4. 감성 점수, 과열도, 키워드, 최근 글 표시
5. 수집 실패 시 mock 데이터 fallback

다음 고도화:
- SQLite/Postgres 저장
- 1~5분 주기 수집 워커 추가
- post URL 기준 중복 제거
- 당일 누적 데이터 기준 감성지수 계산
- KoBERT/KoELECTRA 또는 LLM 감성분류로 교체
        """,
        language="text",
    )

st.caption(f"마지막 화면 렌더링: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
