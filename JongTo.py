import math
import re
import time
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
NAVER_CHART_URL = "https://fchart.stock.naver.com/sise.nhn"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MarketSentimentMVP/0.2; +https://example.com)",
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
    "역대급", "최고가", "신기록", "어닝", "서프라이즈", "개선", "턴어라운드", "바닥", "저점",
    "날라", "날아", "불기둥", "양봉", "쏜다", "오를", "오른", "올라", "상방", "우상향",
    "100만전자", "10만전자", "20만닉스", "엔비디아", "ai", "hbm", "반도체", "탑승", "존버", "추매",
]

NEGATIVE_WORDS = [
    "폭락", "하락", "손절", "물렸다", "물림", "악재", "끝났다", "망했다", "팔아라", "개미지옥",
    "떡락", "하방", "실망", "폭망", "고점", "과열", "조정", "매도", "부진", "적자",
    "리스크", "불안", "급락", "던져", "털림", "횡보", "매물", "약세", "위험", "거품",
    "해소", "무자비", "폭주", "박살", "나락", "답없", "개잡", "물타", "탈출", "지옥", "공매",
    "안오", "못가", "못 간", "글렀", "불가능", "시체", "설거지", "물폭탄", "던진", "순매도",
    "빤스런", "답답", "지겹", "속았", "사기", "무너", "깨짐", "깨진", "추락", "한숨",
]

SARCASM_HINTS = [
    "ㅋㅋ", "ㅎㅎ", "어휴", "휴먼", "인덱스", "최고조", "레전드", "보기 좋", "좋누", "좋네", "잘한다",
    "대단하다", "훌륭하다", "역시", "또", "개미", "안티", "찬티", "비꼬", "웃기", "꼴좋", "선동",
]

FACTUAL_MARKET_HINTS = [
    "미국", "뉴욕", "나스닥", "다우", "s&p", "상승", "하락", "마감", "선물", "환율", "금리", "실적", "공시",
    "외국인", "기관", "개인", "순매수", "순매도", "거래량", "지수", "코스피", "코스닥",
]

OFFTOPIC_HINTS = [
    "민주당", "국민의힘", "정치", "대통령", "방송", "mbc", "청문회", "국회", "선거", "연금", "의대", "축구",
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
        "positive_keywords": {"반등": 92, "실적": 78, "외국인": 65, "매수": 61, "HBM": 55, "저평가": 42},
        "negative_keywords": {"횡보": 68, "물림": 48, "매도": 39, "실망": 34, "하락": 31},
        "posts": [
            {"title": "외국인 다시 들어오는 분위기네요", "sentiment": "긍정", "sentiment_code": "bullish", "confidence": 0.8, "reason": "외국인 유입과 긍정적 분위기 표현.", "views": 482, "likes": 11, "dislikes": 2, "date": "-", "source_page": 1},
            {"title": "오늘 거래량 보면 단기 반등 가능성 있음", "sentiment": "긍정", "sentiment_code": "bullish", "confidence": 0.8, "reason": "반등 가능성 언급.", "views": 331, "likes": 8, "dislikes": 1, "date": "-", "source_page": 1},
            {"title": "또 박스권이면 힘들다", "sentiment": "부정", "sentiment_code": "bearish", "confidence": 0.85, "reason": "박스권 지속 우려.", "views": 298, "likes": 4, "dislikes": 7, "date": "-", "source_page": 1},
            {"title": "휴먼 인덱스 최고조 상태", "sentiment": "부정", "sentiment_code": "sarcastic", "confidence": 0.9, "reason": "비꼼/조롱 표현으로 과열 또는 투자자 심리 악화 의미.", "views": 211, "likes": 2, "dislikes": 1, "date": "-", "source_page": 1},
        ],
        "history_df": pd.DataFrame(),
    }
}

# ------------------------------------------------------------
# 2) 네이버 데이터 수집
# ------------------------------------------------------------

def decode_naver_response(response: requests.Response) -> str:
    """네이버 금융 페이지 한글 깨짐 방지용 디코더.

    Render 환경에서는 requests가 인코딩을 잘못 추정해 종목토론방 제목이
    깨질 수 있으므로 response.text 대신 bytes를 직접 디코딩합니다.
    """
    for encoding in ("cp949", "euc-kr", "utf-8"):
        try:
            return response.content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return response.content.decode("cp949", errors="replace")


def to_int(value: Any) -> int:
    text = str(value).replace(",", "").replace("+", "").strip()
    return int(text) if text.isdigit() else 0


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", str(title)).strip()
    title = title.replace("답글", "").strip()
    return title


@st.cache_data(ttl=180, show_spinner=False)
def fetch_naver_board_pages(stock_code: str, page_count: int = 10, delay_sec: float = 0.15) -> pd.DataFrame:
    """네이버 종목토론방 여러 페이지의 글 목록을 수집합니다.

    해커톤 데모에서는 page_count를 늘려 표본을 확보할 수 있습니다.
    운영 서비스에서는 서비스 정책을 확인하고, 첫 페이지를 주기적으로 누적 수집하는 방식이 더 안전합니다.
    """
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for page in range(1, max(1, page_count) + 1):
        response = requests.get(
            NAVER_BOARD_URL,
            params={"code": stock_code, "page": page},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        html = decode_naver_response(response)

        soup = BeautifulSoup(html, "html.parser")

        for tr in soup.select("table.type2 tr"):
            tds = tr.select("td")
            if len(tds) < 6:
                continue

            cols = [td.get_text(" ", strip=True) for td in tds]
            date_text, title, author, views, likes, dislikes = cols[:6]

            if not re.match(r"^\d{4}\.\d{2}\.\d{2}", date_text):
                continue

            title = clean_title(title)
            if not title:
                continue

            link_tag = tr.select_one("a")
            post_url = ""
            if link_tag and link_tag.get("href"):
                post_url = "https://finance.naver.com" + link_tag["href"]

            dedupe_key = post_url or f"{date_text}|{title}|{author}"
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)

            rows.append(
                {
                    "date": date_text,
                    "title": title,
                    "author": author,
                    "views": to_int(views),
                    "likes": to_int(likes),
                    "dislikes": to_int(dislikes),
                    "url": post_url,
                    "source_page": page,
                }
            )

        if page < page_count:
            time.sleep(delay_sec)

    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_naver_price_info(stock_code: str) -> dict[str, str]:
    response = requests.get(
        NAVER_MAIN_URL,
        params={"code": stock_code},
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    html = decode_naver_response(response)
    soup = BeautifulSoup(html, "html.parser")

    price = "-"
    change = "-"

    price_node = soup.select_one("p.no_today span.blind")
    if price_node:
        price = price_node.get_text(strip=True)

    today_nodes = [node.get_text(strip=True) for node in soup.select("p.no_exday span.blind")]
    if len(today_nodes) >= 2:
        diff = today_nodes[0]
        rate = today_nodes[1]
        change = f"{diff} / {rate}%"

    return {"price": price, "change": change}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_naver_daily_prices(stock_code: str, count: int = 90) -> pd.DataFrame:
    response = requests.get(
        NAVER_CHART_URL,
        params={
            "symbol": stock_code,
            "timeframe": "day",
            "count": count,
            "requestType": 0,
        },
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "xml")
    rows: list[dict[str, Any]] = []

    for item in soup.find_all("item"):
        raw = item.get("data", "")
        parts = raw.split("|")
        if len(parts) < 6:
            continue
        date_raw, open_price, high, low, close, volume = parts[:6]
        rows.append(
            {
                "date": pd.to_datetime(date_raw, format="%Y%m%d", errors="coerce"),
                "open": to_int(open_price),
                "high": to_int(high),
                "low": to_int(low),
                "close": to_int(close),
                "volume": to_int(volume),
            }
        )

    df = pd.DataFrame(rows).dropna(subset=["date"])
    df = df.sort_values("date")

    if not df.empty:
        df["ma5"] = df["close"].rolling(window=5).mean()
        df["ma20"] = df["close"].rolling(window=20).mean()
        df["ma60"] = df["close"].rolling(window=60).mean()

    return df


# ------------------------------------------------------------
# 3) 감성 분석 및 지표 집계
# ------------------------------------------------------------

def has_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def count_hits(text: str, words: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for word in words if word.lower() in lowered)


def classify_sentiment_detail(text: str) -> dict[str, Any]:
    """제목 단위 엄격 분류기.

    핵심 원칙:
    1. 불확실/unknown을 최종 라벨로 내보내지 않습니다.
    2. 중립은 단순 시황·공시·수치 전달에만 제한합니다.
    3. 조롱, 의심, 불만, 질문형, 맥락 없는 짧은 글은 대체로 부정으로 봅니다.
    4. 종목 상승 기대, 매수 의지, 목표가, 반등 기대는 긍정으로 봅니다.
    """
    text = str(text).strip()

    positive_hits = count_hits(text, POSITIVE_WORDS)
    negative_hits = count_hits(text, NEGATIVE_WORDS)
    sarcasm_hits = count_hits(text, SARCASM_HINTS)
    factual_hits = count_hits(text, FACTUAL_MARKET_HINTS)
    offtopic_hits = count_hits(text, OFFTOPIC_HINTS)

    has_laughter = bool(re.search(r"[ㅋㅎ]{2,}", text))
    has_question = any(token in text for token in ["?", "냐", "인가", "맞냐", "노조?", "왜", "뭐냐", "어쩌", "가능?"])
    has_doubt = any(token in text for token in ["아닌", "어렵", "모르", "애매", "불안", "불확", "글쎄", "흠", "과연"])
    has_complaint = any(token in text for token in ["너무", "제발", "그동안", "또", "맨날", "언제", "하...", "아오", "에휴", "휴"])
    has_target_price_up = bool(re.search(r"[0-9]+만전자|[0-9]+만원?간다|[0-9]+만닉스|목표가|신고가|최고가", text))
    has_buy_or_hold = any(token in text for token in ["매수", "추매", "보유", "존버", "탑승", "분할매수", "익절", "수익"])
    has_upward_phrase = any(token in text for token in ["오를", "오른", "올라", "상승", "반등", "간다", "날라", "날아", "쏜다", "불기둥", "양봉"])
    has_downward_phrase = any(token in text for token in ["내릴", "떨어", "하락", "폭락", "손절", "매도", "못가", "안오", "물림", "물렸다"])

    if has_laughter or sarcasm_hits >= 1:
        return {
            "sentiment": "부정",
            "sentiment_code": "sarcastic",
            "score": -0.9,
            "confidence": 0.9,
            "reason": "웃음/비꼼/조롱성 표현은 투자심리 악화로 판단.",
        }

    if has_target_price_up or has_buy_or_hold or has_upward_phrase or (positive_hits >= 1 and positive_hits >= negative_hits):
        confidence = min(0.95, 0.78 + positive_hits * 0.05)
        return {
            "sentiment": "긍정",
            "sentiment_code": "bullish",
            "score": 1.0,
            "confidence": confidence,
            "reason": "상승 기대·목표가·매수/보유 의지 표현이 감지됨.",
        }

    if negative_hits >= 1 or has_downward_phrase or has_question or has_doubt or has_complaint:
        confidence = min(0.95, 0.76 + negative_hits * 0.05)
        return {
            "sentiment": "부정",
            "sentiment_code": "bearish",
            "score": -1.0,
            "confidence": confidence,
            "reason": "우려·불만·의심·하락성 표현이 감지되어 부정으로 판단.",
        }

    is_short_noise = len(text.replace(" ", "")) <= 8
    if factual_hits >= 1 and offtopic_hits == 0 and not is_short_noise:
        return {
            "sentiment": "중립",
            "sentiment_code": "neutral",
            "score": 0.0,
            "confidence": 0.75,
            "reason": "감정보다는 시장/수급/시황 정보 전달에 가까움.",
        }

    if offtopic_hits >= 1:
        return {
            "sentiment": "부정",
            "sentiment_code": "noise_bearish",
            "score": -0.6,
            "confidence": 0.7,
            "reason": "종목과 직접 관련 낮은 잡음성 글로 커뮤니티 심리 악화 요인.",
        }

    return {
        "sentiment": "부정",
        "sentiment_code": "weak_bearish",
        "score": -0.45,
        "confidence": 0.65,
        "reason": "명확한 긍정 근거가 없어 보수적으로 약한 부정 처리.",
    }


def sentiment_to_score(label: str, code: str | None = None) -> float:
    if label == "긍정":
        return 1.0
    if label == "부정":
        return -1.0 if code != "sarcastic" else -0.8
    if label == "불확실":
        return -0.2
    return 0.0


def extract_keywords(posts_df: pd.DataFrame, sentiment_label: str, vocabulary: list[str]) -> dict[str, int]:
    if posts_df.empty or "sentiment" not in posts_df.columns:
        return {}

    filtered = posts_df[posts_df["sentiment"] == sentiment_label]

    result: dict[str, int] = {}

    for word in vocabulary:
        mask = filtered["title"].astype(str).str.contains(re.escape(word), regex=True)
        count = mask.sum()
        if count > 0:
            matched_views = filtered[mask]["views"].sum()
            result[word] = int(count * 20 + math.log1p(matched_views) * 10)

    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:10])


def build_stock_summary(
    stock_code: str,
    stock_name: str,
    posts_df: pd.DataFrame,
    price_info: dict[str, str] | None = None,
    history_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if posts_df.empty:
        raise ValueError("수집된 게시글이 없습니다.")

    df = posts_df.copy()
    details = df["title"].apply(classify_sentiment_detail)
    detail_df = pd.DataFrame(details.tolist())
    df = pd.concat([df.reset_index(drop=True), detail_df.reset_index(drop=True)], axis=1)

    df["weight"] = (
        1
        + df["views"].fillna(0).apply(lambda x: math.log1p(max(x, 0)))
        + df["likes"].fillna(0) * 0.12
        - df["dislikes"].fillna(0) * 0.06
        + df["confidence"].fillna(0.5)
    ).clip(lower=0.2)

    total_weight = df["weight"].sum()
    sentiment_score = 0.0 if total_weight == 0 else float((df["score"] * df["weight"]).sum() / total_weight)

    message_volume = len(df)
    bullish_ratio = round((df["sentiment"] == "긍정").mean() * 100)
    bearish_ratio = round((df["sentiment"] == "부정").mean() * 100)
    neutral_ratio = max(0, 100 - bullish_ratio - bearish_ratio)

    avg_views = df["views"].mean() if message_volume else 0
    total_engagement = df["likes"].sum() + df["dislikes"].sum()
    hype_index = min(100, round(message_volume * 1.6 + math.log1p(avg_views) * 8 + total_engagement * 0.25))

    posts = df[
        [
            "title", "sentiment", "sentiment_code", "confidence", "reason",
            "views", "likes", "dislikes", "date", "source_page", "url",
        ]
    ].head(80).to_dict("records")

    price_info = price_info or {"price": "-", "change": "-"}

    return {
        "name": stock_name,
        "price": price_info.get("price", "-"),
        "change": price_info.get("change", "-"),
        "sentiment_score": sentiment_score,
        "bullish_ratio": bullish_ratio,
        "bearish_ratio": bearish_ratio,
        "neutral_ratio": neutral_ratio,
        "message_volume": message_volume,
        "hype_index": hype_index,
        "updated_at": datetime.now().strftime("%H:%M"),
        "positive_keywords": extract_keywords(df, "긍정", POSITIVE_WORDS),
        "negative_keywords": extract_keywords(df, "부정", NEGATIVE_WORDS + SARCASM_HINTS),
        "posts": posts,
        "raw_posts_df": df,
        "history_df": history_df if history_df is not None else pd.DataFrame(),
    }


def get_sentiment_label(score: float) -> str:
    if score >= 0.35:
        return "긍정 우세"
    if score <= -0.15:
        return "부정 우세"
    return "혼조/중립"


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

    page_count = st.slider(
        "수집 페이지 수",
        min_value=1,
        max_value=20,
        value=10,
        help="해커톤 데모용 표본 수 확대 옵션입니다. 운영에서는 첫 페이지 주기 누적 수집을 권장합니다.",
    )

    chart_days = st.slider("주가 추이 일수", min_value=30, max_value=240, value=90, step=30)

    if st.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("여러 페이지 수집으로 표본을 늘렸습니다.")
    st.caption("감성은 불확실 라벨을 제거하고, 애매한 투자자 심리는 약한 부정으로 엄격 처리합니다.")

# ------------------------------------------------------------
# 5) Data loading
# ------------------------------------------------------------

stock_code = re.sub(r"\D", "", stock_code)[:6] or "005930"
stock_name = find_stock_name(stock_code)
data_source = "mock"
load_error = None

if use_live_data:
    try:
        live_posts_df = fetch_naver_board_pages(stock_code, page_count=page_count)
        price_info = fetch_naver_price_info(stock_code)
        history_df = fetch_naver_daily_prices(stock_code, count=chart_days)
        stock = build_stock_summary(stock_code, stock_name, live_posts_df, price_info, history_df)
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
st.caption("네이버 종목토론방 게시글과 주가 흐름을 함께 보며 커뮤니티 감성지수와 과열도를 추정합니다.")

if data_source == "live":
    st.success(f"실제 네이버 데이터를 수집해 표시 중입니다. 수집 페이지: {page_count}페이지")
elif load_error:
    st.warning(f"실제 데이터 수집에 실패해 mock 데이터로 표시합니다. 오류: {load_error}")
else:
    st.info("mock 데이터로 표시 중입니다.")

header_left, header_right = st.columns([2, 1])

with header_left:
    st.subheader(f"{stock['name']} · {stock_code}")
    st.write(f"현재가 **{stock['price']}원** · 전일대비 **{stock['change']}** · 업데이트 **{stock['updated_at']}**")

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
metric_cols[1].metric("게시글 수", f"{stock['message_volume']:,}", f"{page_count}페이지 기준" if data_source == "live" else "mock 기준")
metric_cols[2].metric("과열도", f"{stock['hype_index']}", "글 수·조회수·추천수")
metric_cols[3].metric("감성 점수", f"{stock['sentiment_score']:+.2f}", "-1 ~ +1")

# ------------------------------------------------------------
# 7) Charts
# ------------------------------------------------------------

price_col, sentiment_col = st.columns([1.4, 1])

with price_col:
    st.subheader("주가 흐름 추이 + 이동평균선")
    history_df = stock.get("history_df", pd.DataFrame())
    if isinstance(history_df, pd.DataFrame) and not history_df.empty:
        available_columns = [col for col in ["close", "ma5", "ma20", "ma60"] if col in history_df.columns]
        price_chart_df = history_df.set_index("date")[available_columns].rename(
            columns={
                "close": "종가",
                "ma5": "5일선",
                "ma20": "20일선",
                "ma60": "60일선",
            }
        )
        st.line_chart(price_chart_df, use_container_width=True)

        latest = history_df.iloc[-1]
        first = history_df.iloc[0]
        period_return = 0.0 if first["close"] == 0 else (latest["close"] / first["close"] - 1) * 100

        ma_caption_parts = []
        if "ma5" in latest and pd.notna(latest["ma5"]):
            ma_caption_parts.append(f"5일선 {int(latest['ma5']):,}원")
        if "ma20" in latest and pd.notna(latest["ma20"]):
            ma_caption_parts.append(f"20일선 {int(latest['ma20']):,}원")
        if "ma60" in latest and pd.notna(latest["ma60"]):
            ma_caption_parts.append(f"60일선 {int(latest['ma60']):,}원")

        st.caption(
            f"기간 수익률: {period_return:+.2f}% · 최근 종가: {int(latest['close']):,}원"
            + (" · " + " · ".join(ma_caption_parts) if ma_caption_parts else "")
        )
    else:
        st.caption("주가 추이 데이터를 불러오지 못했습니다.")

with sentiment_col:
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

chart_col_1, chart_col_2 = st.columns([1, 1])

with chart_col_1:
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

with chart_col_2:
    st.subheader("분류 코드 분포")
    raw_df = stock.get("raw_posts_df", pd.DataFrame())
    if isinstance(raw_df, pd.DataFrame) and not raw_df.empty and "sentiment_code" in raw_df.columns:
        code_df = raw_df["sentiment_code"].value_counts().reset_index()
        code_df.columns = ["code", "count"]
        st.bar_chart(code_df, x="code", y="count")
    else:
        st.caption("분류 코드 데이터가 없습니다.")

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
        "sentiment": "문장 감성",
        "sentiment_code": "감성 코드",
        "confidence": st.column_config.NumberColumn("신뢰도", format="%.2f"),
        "reason": "판단 근거",
        "views": "조회",
        "likes": "추천",
        "dislikes": "비추천",
        "date": "작성일시",
        "source_page": "수집 페이지",
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
# 9) Backend connection guide
# ------------------------------------------------------------

with st.expander("현재 MVP 구조 보기"):
    st.code(
        """
현재 버전:
1. Streamlit app.py 실행
2. 네이버 종목토론방 여러 페이지 수집
3. 제목 기반 보수적 감성분석
   - 조롱/반어/비꼼: 부정 계열
   - 판단 어려움: 중립 대신 불확실로 분리
4. 네이버 주가 차트 XML에서 일봉 종가 추이 수집
5. 감성 점수, 과열도, 키워드, 최근 글, 주가 흐름 표시

다음 고도화:
- 페이지 대량 수집 대신 1~5분 주기 누적 수집 워커 추가
- SQLite/Postgres 저장
- post URL 기준 중복 제거
- 당일 누적 데이터 기준 감성지수 계산
- OpenAI API/KoELECTRA/KoBERT 감성분류로 교체
        """,
        language="text",
    )

st.caption(f"마지막 화면 렌더링: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
