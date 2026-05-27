import math
import re
import time
from collections import Counter
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
NAVER_MAIN_URL = "https://finance.naver.com/item/main.naver"

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
    "날아", "올라", "오른다", "오름", "매집", "추매", "바닥", "턴어라운드", "기회", "상방",
    "대박", "좋네", "좋음", "갈듯", "간다", "쏜다", "양봉", "익절", "돌파", "강력",
]

NEGATIVE_WORDS = [
    "폭락", "하락", "손절", "물렸다", "물림", "악재", "끝났다", "망했다", "팔아라", "개미지옥",
    "떡락", "하방", "실망", "폭망", "고점", "과열", "조정", "매도", "부진", "적자",
    "리스크", "불안", "급락", "던져", "털림", "횡보", "매물", "약세", "위험", "거품",
    "물타기", "물렸", "빠진다", "내린다", "손실", "시체", "나락", "답없", "망함",
    "음봉", "하따", "물량", "개미무덤", "폭망", "폭탄", "손절", "탈출", "지옥",
]

STOPWORDS = {
    "그리고", "그러나", "그래서", "하지만", "오늘", "내일", "어제", "지금", "진짜", "정말",
    "너무", "매우", "계속", "그냥", "아직", "다시", "이번", "저번", "이제", "여기",
    "저기", "이거", "저거", "그거", "뭐냐", "뭔가", "때문", "대한", "관련", "종목",
    "주식", "주가", "시장", "사람", "개미", "님들", "형들", "ㅋㅋ", "ㅎㅎ", "ㅠㅠ",
    "있다", "없다", "한다", "된다", "같다", "보다", "하면", "해서", "하는", "이런",
    "저런", "그런", "아니", "하나", "이건", "이게", "그게", "ㅋㅋㅋ", "ㅎㅎㅎ",
    "삼성전자", "하이닉스", "네이버", "카카오", "현대차", "LG화학", "셀트리온",
}

MOCK_STOCK = {
    "name": "삼성전자",
    "price": "74,200",
    "change": "+1.23%",
    "change_text": "상승 1.23%",
    "sentiment_score": 0.42,
    "bullish_ratio": 58,
    "bearish_ratio": 24,
    "neutral_ratio": 18,
    "message_volume": 184,
    "hype_index": 76,
    "updated_at": "오늘 14:35",
    "top_keywords": [
        {"keyword": "반등", "count": 12, "score": 92, "sentiment": "긍정"},
        {"keyword": "실적", "count": 9, "score": 78, "sentiment": "관심"},
        {"keyword": "외국인", "count": 7, "score": 65, "sentiment": "관심"},
        {"keyword": "매수", "count": 6, "score": 61, "sentiment": "긍정"},
        {"keyword": "횡보", "count": 4, "score": 48, "sentiment": "부정"},
    ],
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
    ],
}

# ------------------------------------------------------------
# 2) 공통 유틸
# ------------------------------------------------------------

def to_int(value: Any) -> int:
    text = str(value).replace(",", "").replace("+", "").replace("-", "").strip()
    return int(text) if text.isdigit() else 0


def decode_naver_html(content: bytes) -> str:
    for encoding in ["cp949", "euc-kr", "utf-8"]:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue

    return content.decode("cp949", errors="replace")


def clean_text(text: str) -> str:
    text = str(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_title(title: str) -> str:
    title = clean_text(title)
    title = title.replace("답글", "")
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = re.sub(r"\([^)]*\)", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def find_stock_name(stock_code: str) -> str:
    return STOCK_PRESETS.get(stock_code, f"종목 {stock_code}")


# ------------------------------------------------------------
# 3) 현재가 / 등락률 수집
# ------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def fetch_stock_price(stock_code: str) -> dict[str, str]:
    response = requests.get(
        NAVER_MAIN_URL,
        params={"code": stock_code},
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()

    html = decode_naver_html(response.content)
    soup = BeautifulSoup(html, "html.parser")

    name = find_stock_name(stock_code)

    name_tag = soup.select_one("div.wrap_company h2")
    if name_tag:
        name = clean_text(name_tag.get_text())

    price = "-"
    price_tag = soup.select_one("p.no_today span.blind")
    if price_tag:
        price = clean_text(price_tag.get_text())

    change_value = "-"
    change_rate = "-"
    change_direction = "보합"

    exday = soup.select_one("p.no_exday")
    if exday:
        blind_values = [
            clean_text(tag.get_text())
            for tag in exday.select("span.blind")
            if clean_text(tag.get_text())
        ]

        if len(blind_values) >= 1:
            change_value = blind_values[0]

        if len(blind_values) >= 2:
            change_rate = blind_values[1]

        exday_text = clean_text(exday.get_text(" "))

        if "상승" in exday_text:
            change_direction = "상승"
        elif "하락" in exday_text:
            change_direction = "하락"
        else:
            change_direction = "보합"

    if change_value == "-" and change_rate == "-":
        change_text = "-"
        change_display = "-"
    else:
        sign = "+"
        if change_direction == "하락":
            sign = "-"
        elif change_direction == "보합":
            sign = ""

        change_text = f"{change_direction} {change_value} / {change_rate}%"
        change_display = f"{sign}{change_rate}%"

    return {
        "name": name,
        "price": price,
        "change": change_display,
        "change_text": change_text,
    }


# ------------------------------------------------------------
# 4) 종목토론방 여러 페이지 수집
# ------------------------------------------------------------

@st.cache_data(ttl=180, show_spinner=False)
def fetch_naver_board_pages(stock_code: str, max_pages: int = 3) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    max_pages = max(1, min(int(max_pages), 5))

    for page in range(1, max_pages + 1):
        response = requests.get(
            NAVER_BOARD_URL,
            params={"code": stock_code, "page": page},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()

        html = decode_naver_html(response.content)
        soup = BeautifulSoup(html, "html.parser")

        for tr in soup.select("table.type2 tr"):
            tds = tr.select("td")
            if len(tds) < 6:
                continue

            cols = [clean_text(td.get_text(" ", strip=True)) for td in tds]
            date_text = cols[0]

            if not re.match(r"^\d{4}\.\d{2}\.\d{2}", date_text):
                continue

            link_tag = tr.select_one("a")

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
                    "page": page,
                }
            )

        time.sleep(0.25)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    if "url" in df.columns:
        df = df.drop_duplicates(subset=["url"], keep="first")

    df = df.drop_duplicates(subset=["date", "title"], keep="first")
    df = df.reset_index(drop=True)

    return df


# ------------------------------------------------------------
# 5) 감성 분석
# ------------------------------------------------------------

def count_hits(text: str, words: list[str]) -> int:
    text = str(text)
    return sum(1 for word in words if word in text)


def classify_sentiment(text: str) -> str:
    positive_hits = count_hits(text, POSITIVE_WORDS)
    negative_hits = count_hits(text, NEGATIVE_WORDS)

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


def get_sentiment_label(score: float) -> str:
    if score >= 0.25:
        return "긍정 우세"

    if score <= -0.25:
        return "부정 우세"

    return "중립"


# ------------------------------------------------------------
# 6) 실시간 빈출 키워드 추출
# ------------------------------------------------------------

def tokenize_korean_title(text: str) -> list[str]:
    text = clean_text(text)

    # 한글, 영어, 숫자만 남김
    candidates = re.findall(r"[가-힣A-Za-z0-9]{2,}", text)

    tokens = []
    for token in candidates:
        token = token.strip()

        if len(token) < 2:
            continue

        if token in STOPWORDS:
            continue

        if token.isdigit():
            continue

        # 너무 일반적인 종결 표현 제거
        if token.endswith(("네요", "합니다", "는데", "듯요", "인가", "이냐", "냐고")) and len(token) <= 4:
            continue

        tokens.append(token)

    return tokens


def keyword_sentiment(keyword: str) -> str:
    pos = count_hits(keyword, POSITIVE_WORDS)
    neg = count_hits(keyword, NEGATIVE_WORDS)

    if pos > neg:
        return "긍정"

    if neg > pos:
        return "부정"

    return "관심"


def extract_realtime_keywords(posts_df: pd.DataFrame, top_n: int = 20) -> list[dict[str, Any]]:
    if posts_df.empty:
        return []

    counter = Counter()
    view_counter = Counter()
    like_counter = Counter()
    dislike_counter = Counter()

    for _, row in posts_df.iterrows():
        title = str(row.get("title", ""))
        tokens = tokenize_korean_title(title)

        for token in tokens:
            counter[token] += 1
            view_counter[token] += int(row.get("views", 0) or 0)
            like_counter[token] += int(row.get("likes", 0) or 0)
            dislike_counter[token] += int(row.get("dislikes", 0) or 0)

    results = []

    for keyword, count in counter.items():
        views = view_counter[keyword]
        likes = like_counter[keyword]
        dislikes = dislike_counter[keyword]

        score = (
            count * 20
            + math.log1p(views) * 8
            + likes * 2
            - dislikes
        )

        results.append(
            {
                "keyword": keyword,
                "count": int(count),
                "score": round(score, 1),
                "sentiment": keyword_sentiment(keyword),
                "views": int(views),
                "likes": int(likes),
                "dislikes": int(dislikes),
            }
        )

    results = sorted(results, key=lambda x: (x["count"], x["score"]), reverse=True)
    return results[:top_n]


def keyword_sentiment_score(top_keywords: list[dict[str, Any]]) -> float:
    if not top_keywords:
        return 0.0

    total_score = sum(max(float(item["score"]), 0.1) for item in top_keywords)
    if total_score == 0:
        return 0.0

    weighted = 0.0

    for item in top_keywords:
        sentiment = item["sentiment"]
        score = max(float(item["score"]), 0.1)

        if sentiment == "긍정":
            weighted += score
        elif sentiment == "부정":
            weighted -= score

    return weighted / total_score


# ------------------------------------------------------------
# 7) 지표 집계
# ------------------------------------------------------------

def build_stock_summary(
    stock_code: str,
    stock_name: str,
    price_info: dict[str, str],
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
        post_sentiment_score = 0.0
    else:
        post_sentiment_score = float(
            (df["sentiment_value"] * df["weight"]).sum() / total_weight
        )

    top_keywords = extract_realtime_keywords(df, top_n=20)
    keyword_score = keyword_sentiment_score(top_keywords)

    # 게시글 감성 70%, 실시간 키워드 감성 30%
    final_sentiment_score = post_sentiment_score * 0.7 + keyword_score * 0.3

    message_volume = len(df)
    bullish_ratio = round((df["sentiment"] == "긍정").mean() * 100)
    bearish_ratio = round((df["sentiment"] == "부정").mean() * 100)
    neutral_ratio = 100 - bullish_ratio - bearish_ratio

    avg_views = df["views"].mean() if message_volume else 0
    total_engagement = df["likes"].sum() + df["dislikes"].sum()

    hype_index = min(
        100,
        round(
            message_volume * 1.5
            + math.log1p(avg_views) * 9
            + total_engagement * 0.25
        ),
    )

    posts = df[
        ["title", "sentiment", "views", "likes", "dislikes", "date", "url", "page"]
    ].head(50).to_dict("records")

    return {
        "name": price_info.get("name") or stock_name,
        "price": price_info.get("price", "-"),
        "change": price_info.get("change", "-"),
        "change_text": price_info.get("change_text", "-"),
        "sentiment_score": final_sentiment_score,
        "post_sentiment_score": post_sentiment_score,
        "keyword_sentiment_score": keyword_score,
        "bullish_ratio": bullish_ratio,
        "bearish_ratio": bearish_ratio,
        "neutral_ratio": neutral_ratio,
        "message_volume": message_volume,
        "hype_index": hype_index,
        "updated_at": datetime.now().strftime("%H:%M"),
        "top_keywords": top_keywords,
        "posts": posts,
        "raw_posts_df": df,
    }


def keyword_dataframe(top_keywords: list[dict[str, Any]]) -> pd.DataFrame:
    if not top_keywords:
        return pd.DataFrame(
            columns=["keyword", "count", "score", "sentiment", "views", "likes", "dislikes"]
        )

    return pd.DataFrame(top_keywords)


def render_keyword_chips(top_keywords: list[dict[str, Any]]) -> None:
    if not top_keywords:
        st.caption("아직 충분한 키워드가 감지되지 않았습니다.")
        return

    max_score = max(float(item["score"]) for item in top_keywords) or 1

    html = "<div style='display:flex;flex-wrap:wrap;gap:8px;'>"

    for item in top_keywords[:20]:
        keyword = item["keyword"]
        score = float(item["score"])
        sentiment = item["sentiment"]
        count = item["count"]

        size = 13 + math.floor((score / max_score) * 10)

        if sentiment == "긍정":
            bg = "#dcfce7"
            color = "#166534"
        elif sentiment == "부정":
            bg = "#fee2e2"
            color = "#991b1b"
        else:
            bg = "#f1f5f9"
            color = "#334155"

        html += (
            f"<span title='빈도 {count}회 / 점수 {score}' "
            f"style='font-size:{size}px;"
            f"background:{bg};"
            "padding:7px 11px;"
            "border-radius:999px;"
            "font-weight:700;"
            f"color:{color};'>"
            f"#{keyword}"
            "</span>"
        )

    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------------------
# 8) 사이드바
# ------------------------------------------------------------

with st.sidebar:
    st.header("데이터 설정")

    stock_options = [f"{code} · {name}" for code, name in STOCK_PRESETS.items()]
    selected_option = st.selectbox("종목 선택", stock_options)
    selected_code = selected_option.split(" · ")[0]

    stock_code = st.text_input(
        "종목코드 직접 입력",
        value=selected_code,
        placeholder="예: 005930",
        max_chars=6,
    )

    max_pages = st.slider(
        "수집 페이지 수",
        min_value=1,
        max_value=5,
        value=3,
        step=1,
        help="해커톤 데모에서는 2~3페이지를 권장합니다.",
    )

    use_live_data = st.toggle("실제 네이버 데이터 수집", value=True)

    if st.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("현재가와 등락률은 네이버 금융 종목 메인에서 가져옵니다.")
    st.caption("종목토론방은 선택한 페이지 수만큼 최신 글을 수집합니다.")
    st.caption("수집 실패 시 mock 데이터로 자동 전환됩니다.")

# ------------------------------------------------------------
# 9) 데이터 로딩
# ------------------------------------------------------------

stock_code = re.sub(r"\D", "", stock_code)[:6] or "005930"
stock_name = find_stock_name(stock_code)

data_source = "mock"
load_error = None

if use_live_data:
    try:
        price_info = fetch_stock_price(stock_code)
        live_posts_df = fetch_naver_board_pages(stock_code, max_pages=max_pages)

        stock = build_stock_summary(
            stock_code=stock_code,
            stock_name=stock_name,
            price_info=price_info,
            posts_df=live_posts_df,
        )

        data_source = "live"

    except Exception as exc:
        load_error = str(exc)
        stock = MOCK_STOCK.copy()
else:
    stock = MOCK_STOCK.copy()

# ------------------------------------------------------------
# 10) 메인 화면
# ------------------------------------------------------------

st.title("📈 종목토론방 실시간 여론 대시보드")
st.caption(
    "네이버 종목토론방의 최신 게시글 제목을 기반으로 "
    "현재가, 등락률, 커뮤니티 감성지수, 빈출 키워드, 과열도를 추정합니다."
)

if data_source == "live":
    st.success(
        f"실제 네이버 데이터를 수집해 표시 중입니다. "
        f"종목토론방 {max_pages}페이지 기준입니다."
    )
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
        f"상세 **{stock.get('change_text', '-')}** · "
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
    f"{max_pages}페이지 기준" if data_source == "live" else "mock 기준",
)

metric_cols[2].metric(
    "과열도",
    f"{stock['hype_index']}",
    "글 수·조회수·추천수",
)

metric_cols[3].metric(
    "감성 점수",
    f"{stock['sentiment_score']:+.2f}",
    "게시글 70% + 키워드 30%",
)

score_cols = st.columns(2)

with score_cols[0]:
    st.metric(
        "게시글 기반 감성",
        f"{stock.get('post_sentiment_score', stock['sentiment_score']):+.2f}",
    )

with score_cols[1]:
    st.metric(
        "빈출 키워드 기반 감성",
        f"{stock.get('keyword_sentiment_score', 0):+.2f}",
    )

# ------------------------------------------------------------
# 11) 차트
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
    st.subheader("실시간 빈출 키워드 랭킹")

    keyword_df = keyword_dataframe(stock.get("top_keywords", []))

    st.dataframe(
        keyword_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "keyword": "키워드",
            "count": "빈도",
            "score": "가중치",
            "sentiment": "키워드 감성",
            "views": "조회 합",
            "likes": "추천 합",
            "dislikes": "비추천 합",
        },
    )

st.subheader("실시간 키워드 클라우드")
render_keyword_chips(stock.get("top_keywords", []))

st.divider()

# ------------------------------------------------------------
# 12) 최근 글
# ------------------------------------------------------------

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
        "page": "수집 페이지",
    },
)

if data_source == "live" and not posts_df.empty and "url" in posts_df.columns:
    with st.expander("게시글 링크 보기"):
        for _, row in posts_df.head(20).iterrows():
            if row.get("url"):
                st.markdown(f"- [{row['title']}]({row['url']})")

st.warning(
    "본 지표는 네이버 종목토론방 게시글 기반의 비정형 커뮤니티 감성 분석 결과이며, "
    "투자 권유나 매매 신호가 아닙니다."
)

# ------------------------------------------------------------
# 13) 설명
# ------------------------------------------------------------

with st.expander("현재 MVP 구조 보기"):
    st.code(
        """
현재 버전:
1. 네이버 금융 종목 메인에서 현재가와 등락률 수집
2. 네이버 종목토론방에서 선택한 페이지 수만큼 최신 글 수집
3. 제목 기반 룰 감성분석
4. 실제 제목에서 빈출 키워드 추출
5. 빈출 키워드를 긍정/부정/관심으로 분류
6. 게시글 감성 70% + 키워드 감성 30%로 최종 감성 점수 계산

주의:
- 페이지 수를 과도하게 늘리지 않는 것이 좋습니다.
- 실제 서비스에서는 주기적 수집 + DB 누적 방식이 더 안정적입니다.
        """,
        language="text",
    )

st.caption(f"마지막 화면 렌더링: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
