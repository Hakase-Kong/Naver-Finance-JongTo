import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
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

# ============================================================
# 1) 기본 설정
# ============================================================

NAVER_BOARD_URL = "https://finance.naver.com/item/board.naver"
NAVER_MAIN_URL = "https://finance.naver.com/item/main.naver"
NAVER_CHART_URL = "https://fchart.stock.naver.com/sise.nhn"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MarketSentimentMVP/0.4)",
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

# 긍정/부정 단어는 계속 보강할 수 있습니다.
POSITIVE_WORDS = [
    "상한가", "급등", "간다", "가즈아", "매수", "호재", "돌파", "신고가", "반등", "대박",
    "상승", "불장", "기대", "저평가", "수급", "실적", "목표가", "외국인", "기관", "강세",
    "랠리", "회복", "성장", "수혜", "흑자", "계약", "수주", "좋다", "버틴다", "추세",
    "역대급", "최고가", "신기록", "어닝", "서프라이즈", "개선", "턴어라운드", "바닥", "저점",
    "날라", "날아", "불기둥", "양봉", "쏜다", "오를", "오른", "올라", "상방", "우상향",
    "100만전자", "10만전자", "20만닉스", "엔비디아", "ai", "hbm", "반도체", "탑승", "존버", "추매",
    "공급", "승인", "수주", "개발", "증설", "수혜", "랠리", "대장", "주도주", "매집",
]

NEGATIVE_WORDS = [
    "폭락", "하락", "손절", "물렸다", "물림", "악재", "끝났다", "망했다", "팔아라", "개미지옥",
    "떡락", "하방", "실망", "폭망", "고점", "과열", "조정", "매도", "부진", "적자",
    "리스크", "불안", "급락", "던져", "털림", "횡보", "매물", "약세", "위험", "거품",
    "해소", "무자비", "폭주", "박살", "나락", "답없", "개잡", "물타", "탈출", "지옥", "공매",
    "안오", "못가", "못 간", "글렀", "불가능", "시체", "설거지", "물폭탄", "던진", "순매도",
    "빤스런", "답답", "지겹", "속았", "사기", "무너", "깨짐", "깨진", "추락", "한숨",
    "무섭", "무서운", "전쟁", "불승인", "취소", "반대", "압박", "규제", "소송", "위기", "손실",
]

SARCASM_HINTS = [
    "ㅋㅋ", "ㅎㅎ", "어휴", "에휴", "휴먼", "인덱스", "최고조", "레전드", "보기 좋", "좋누", "좋네",
    "잘한다", "대단하다", "훌륭하다", "역시", "또", "안티", "찬티", "비꼬", "웃기", "꼴좋", "선동",
]

FACTUAL_MARKET_HINTS = [
    "미국", "뉴욕", "나스닥", "다우", "s&p", "상승", "하락", "마감", "선물", "환율", "금리", "실적", "공시",
    "외국인", "기관", "개인", "순매수", "순매도", "거래량", "지수", "코스피", "코스닥", "장전", "장중",
]

OFFTOPIC_HINTS = [
    "민주당", "국민의힘", "정치", "대통령", "방송", "mbc", "청문회", "국회", "선거", "연금", "의대", "축구",
    "노조", "전쟁", "북한", "트럼프", "이재명", "윤석열", "한동훈", "박정희", "김건희",
]

STOPWORDS = {
    "오늘", "내일", "지금", "이번", "저번", "그냥", "정말", "진짜", "너무", "계속", "다시",
    "삼성", "삼성전자", "전자", "하이닉스", "네이버", "카카오", "주식", "종목", "주가", "사람",
    "합니다", "있다", "있는", "없는", "네요", "인가요", "가나요", "입니다", "그리고", "근데",
    "ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "ㅜㅜ", "이제", "여기", "그거", "이거", "저거", "대한", "때문",
}

MOCK_HISTORY = pd.DataFrame(
    {
        "date": pd.date_range(end=pd.Timestamp.today(), periods=90),
        "close": [70000 + i * 30 + int(math.sin(i / 5) * 1500) for i in range(90)],
    }
)
MOCK_HISTORY["ma5"] = MOCK_HISTORY["close"].rolling(5).mean()
MOCK_HISTORY["ma20"] = MOCK_HISTORY["close"].rolling(20).mean()
MOCK_HISTORY["ma60"] = MOCK_HISTORY["close"].rolling(60).mean()

MOCK_POSTS = pd.DataFrame(
    [
        {"date": "-", "title": "외국인 다시 들어오는 분위기네요", "author": "-", "views": 482, "likes": 11, "dislikes": 2, "url": "", "source_page": 1},
        {"date": "-", "title": "오늘 거래량 보면 단기 반등 가능성 있음", "author": "-", "views": 331, "likes": 8, "dislikes": 1, "url": "", "source_page": 1},
        {"date": "-", "title": "또 박스권이면 힘들다", "author": "-", "views": 298, "likes": 4, "dislikes": 7, "url": "", "source_page": 1},
        {"date": "-", "title": "휴먼 인덱스 최고조 상태 ㅋㅋ", "author": "-", "views": 211, "likes": 2, "dislikes": 1, "url": "", "source_page": 1},
    ]
)

# ============================================================
# 2) 네이버 수집 유틸
# ============================================================

def decode_naver_response(response: requests.Response) -> str:
    """네이버 금융 페이지 한글 깨짐 방지용 디코더."""
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
    title = re.sub(r"\[\d+\]$", "", title).strip()
    return title


@st.cache_data(ttl=180, show_spinner=False)
def fetch_naver_board_pages(stock_code: str, page_count: int = 10, delay_sec: float = 0.12) -> pd.DataFrame:
    """네이버 종목토론방 여러 페이지의 글 목록을 수집합니다.

    source_page 컬럼은 해당 글이 몇 페이지에서 수집됐는지 뜻합니다.
    예: source_page=4는 4페이지 글이라는 의미입니다.
    """
    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

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
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

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

    rows: list[dict[str, Any]] = []
    root = ET.fromstring(response.content)

    for item in root.iter("item"):
        raw = item.attrib.get("data", "")
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
        df["volume_ma20"] = df["volume"].rolling(window=20).mean()

    return df

# ============================================================
# 3) 감성 분석: 룰 기반 + 선택적 LLM
# ============================================================

def has_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def count_hits(text: str, words: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for word in words if word.lower() in lowered)


def classify_sentiment_rule(title: str, stock_name: str) -> dict[str, Any]:
    """제목을 해당 종목 관점에서 긍정/부정/중립으로 분류합니다.

    내부 코드는 더 세분화하지만 화면 라벨은 긍정/부정/중립만 사용합니다.
    """
    text = str(title).strip()

    positive_hits = count_hits(text, POSITIVE_WORDS)
    negative_hits = count_hits(text, NEGATIVE_WORDS)
    sarcasm_hits = count_hits(text, SARCASM_HINTS)
    factual_hits = count_hits(text, FACTUAL_MARKET_HINTS)
    offtopic_hits = count_hits(text, OFFTOPIC_HINTS)

    has_laughter = bool(re.search(r"[ㅋㅎ]{2,}", text))
    has_question = any(token in text for token in ["?", "냐", "인가", "맞냐", "왜", "뭐냐", "어쩌", "가능?"])
    has_doubt = any(token in text for token in ["아닌", "어렵", "모르", "애매", "불안", "불확", "글쎄", "흠", "과연"])
    has_complaint = any(token in text for token in ["제발", "그동안", "맨날", "하...", "아오", "에휴"])
    has_target_price_up = bool(re.search(r"[0-9]+만전자|[0-9]+만원?간다|[0-9]+만닉스|목표가|신고가|최고가", text))
    has_buy_or_hold = any(token in text for token in ["매수", "추매", "보유", "존버", "탑승", "분할매수", "익절", "수익"])
    has_upward_phrase = any(token in text for token in ["오를", "오른", "올라", "상승", "반등", "간다", "날라", "날아", "쏜다", "불기둥", "양봉"])
    has_downward_phrase = any(token in text for token in ["내릴", "떨어", "하락", "폭락", "손절", "매도", "못가", "안오", "물림", "물렸다"])
    is_short_text = len(text.replace(" ", "")) <= 8

    positive_score = positive_hits * 2.0
    negative_score = negative_hits * 2.0

    if has_target_price_up:
        positive_score += 3.0
    if has_buy_or_hold:
        positive_score += 2.5
    if has_upward_phrase:
        positive_score += 2.0

    if has_downward_phrase:
        negative_score += 3.0
    if has_doubt:
        negative_score += 1.2
    if has_complaint:
        negative_score += 1.8
    if has_question:
        negative_score += 0.3
    if sarcasm_hits >= 1 or has_laughter:
        negative_score += 1.5

    # 상승 키워드 + 웃음은 단순 흥분일 수 있어 바로 부정 처리하지 않습니다.
    if (sarcasm_hits >= 1 or has_laughter) and negative_score > positive_score + 2.0:
        return {
            "sentiment": "부정",
            "sentiment_code": "sarcastic_bearish",
            "score": -0.85,
            "confidence": 0.86,
            "reason": "비꼼/조롱성 표현과 부정 맥락이 함께 감지됨.",
            "is_noise": False,
        }

    if positive_score >= negative_score + 1.5:
        return {
            "sentiment": "긍정",
            "sentiment_code": "strong_bullish" if positive_score >= 4 else "weak_bullish",
            "score": 1.0 if positive_score >= 4 else 0.65,
            "confidence": min(0.93, 0.68 + positive_score * 0.05),
            "reason": f"{stock_name} 관점에서 상승 기대·목표가·매수/보유 의지 표현이 우세함.",
            "is_noise": False,
        }

    if negative_score >= positive_score + 1.5:
        return {
            "sentiment": "부정",
            "sentiment_code": "strong_bearish" if negative_score >= 4 else "weak_bearish",
            "score": -1.0 if negative_score >= 4 else -0.65,
            "confidence": min(0.93, 0.68 + negative_score * 0.05),
            "reason": f"{stock_name} 관점에서 우려·불만·하락성 표현이 우세함.",
            "is_noise": False,
        }

    if factual_hits >= 1 and offtopic_hits == 0:
        return {
            "sentiment": "중립",
            "sentiment_code": "neutral_info",
            "score": 0.0,
            "confidence": 0.76,
            "reason": "감정보다는 시장/수급/시황 정보 전달에 가까움.",
            "is_noise": False,
        }

    if offtopic_hits >= 1:
        return {
            "sentiment": "중립",
            "sentiment_code": "neutral_noise",
            "score": 0.0,
            "confidence": 0.64,
            "reason": "종목 감성과 직접 연결하기 어려운 비시장성/잡음성 주제.",
            "is_noise": True,
        }

    if is_short_text or has_question:
        return {
            "sentiment": "중립",
            "sentiment_code": "neutral_chat",
            "score": 0.0,
            "confidence": 0.64,
            "reason": "방향성이 약한 질문/짧은 잡담으로 중립 처리.",
            "is_noise": False,
        }

    return {
        "sentiment": "중립",
        "sentiment_code": "neutral_weak",
        "score": 0.0,
        "confidence": 0.60,
        "reason": "긍정/부정 근거가 비슷하거나 부족해 중립 처리.",
        "is_noise": False,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def classify_sentiment_llm_cached(title: str, stock_name: str, model_name: str) -> dict[str, Any]:
    """선택적 LLM 분류. OPENAI_API_KEY와 openai 패키지가 있을 때만 사용됩니다."""
    try:
        from openai import OpenAI
    except Exception:
        return classify_sentiment_rule(title, stock_name)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return classify_sentiment_rule(title, stock_name)

    client = OpenAI(api_key=api_key)

    system_prompt = """
너는 한국 주식 커뮤니티 문장을 해당 종목 관점에서 분류하는 감성 분석기다.
반드시 JSON만 출력한다.
라벨은 bullish, bearish, neutral 중 하나다.
판단 기준:
- 해당 종목 주가, 실적, 수급, 기대감에 긍정적이면 bullish.
- 하락 우려, 손절, 고점 경계, 악재, 조롱, 비꼼, 불만이면 bearish.
- 단순 시황/정보/정치/잡담/종목과 무관한 글이면 neutral.
- 정치/사회/잡담성 글은 is_noise=true로 표시한다.
"""

    user_prompt = f"""
종목명: {stock_name}
게시글 제목: {title}

다음 JSON 형식으로만 답해라.
{{
  "label": "bullish|bearish|neutral",
  "code": "strong_bullish|weak_bullish|strong_bearish|weak_bearish|neutral_info|neutral_noise|neutral_chat",
  "confidence": 0.0,
  "reason": "한국어 한 문장 근거",
  "is_noise": false
}}
"""

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content)

        label = str(parsed.get("label", "neutral")).lower()
        code = str(parsed.get("code", "neutral_info"))
        confidence = float(parsed.get("confidence", 0.7))
        reason = str(parsed.get("reason", "LLM 판단"))
        is_noise = bool(parsed.get("is_noise", False))

        if label == "bullish":
            sentiment = "긍정"
            score = 1.0 if "strong" in code else 0.65
        elif label == "bearish":
            sentiment = "부정"
            score = -1.0 if "strong" in code else -0.65
        else:
            sentiment = "중립"
            score = 0.0

        return {
            "sentiment": sentiment,
            "sentiment_code": code,
            "score": score,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": reason,
            "is_noise": is_noise,
        }
    except Exception:
        return classify_sentiment_rule(title, stock_name)


def classify_title(title: str, stock_name: str, mode: str, model_name: str) -> dict[str, Any]:
    if mode == "LLM" and os.getenv("OPENAI_API_KEY"):
        return classify_sentiment_llm_cached(title, stock_name, model_name)
    return classify_sentiment_rule(title, stock_name)

# ============================================================
# 4) 집계/키워드/해석
# ============================================================

def extract_keywords(posts_df: pd.DataFrame, sentiment_label: str, vocabulary: list[str]) -> dict[str, int]:
    if posts_df.empty or "sentiment" not in posts_df.columns:
        return {}

    filtered = posts_df[posts_df["sentiment"] == sentiment_label]
    result: dict[str, int] = {}

    for word in vocabulary:
        mask = filtered["title"].astype(str).str.contains(re.escape(word), regex=True, case=False)
        count = int(mask.sum())
        if count > 0:
            matched_views = int(filtered[mask]["views"].sum()) if "views" in filtered.columns else 0
            result[word] = int(count * 20 + math.log1p(matched_views) * 10)

    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:12])


def extract_frequent_terms(posts_df: pd.DataFrame, top_n: int = 50) -> dict[str, int]:
    """감성과 무관하게 전체 게시글 제목에서 빈출 어휘를 추출합니다."""
    if posts_df.empty or "title" not in posts_df.columns:
        return {}

    counter: dict[str, int] = {}
    titles = " ".join(posts_df["title"].astype(str).tolist()).lower()

    tokens = re.findall(r"[가-힣a-zA-Z0-9]{2,}", titles)
    for token in tokens:
        token = token.strip().lower()
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        counter[token] = counter.get(token, 0) + 1

    domain_terms = POSITIVE_WORDS + NEGATIVE_WORDS + SARCASM_HINTS + FACTUAL_MARKET_HINTS
    for word in domain_terms:
        if len(word) < 2:
            continue
        normalized = word.lower()
        if normalized in STOPWORDS:
            continue
        count = titles.count(normalized)
        if count > 0:
            counter[word] = counter.get(word, 0) + count * 2

    return dict(sorted(counter.items(), key=lambda x: x[1], reverse=True)[:top_n])


def build_stock_summary(
    stock_code: str,
    stock_name: str,
    posts_df: pd.DataFrame,
    price_info: dict[str, str] | None,
    history_df: pd.DataFrame | None,
    classification_mode: str,
    llm_model_name: str,
) -> dict[str, Any]:
    if posts_df.empty:
        raise ValueError("수집된 게시글이 없습니다.")

    df = posts_df.copy().reset_index(drop=True)
    details = df["title"].apply(lambda title: classify_title(title, stock_name, classification_mode, llm_model_name))
    detail_df = pd.DataFrame(details.tolist())
    df = pd.concat([df, detail_df], axis=1)

    # noise는 감성 점수 가중치를 낮춥니다.
    df["base_weight"] = (
        1
        + df["views"].fillna(0).apply(lambda x: math.log1p(max(int(x), 0)))
        + df["likes"].fillna(0) * 0.10
        - df["dislikes"].fillna(0) * 0.04
    ).clip(lower=0.2)
    df["noise_weight"] = df["is_noise"].apply(lambda value: 0.25 if value else 1.0)
    df["weight"] = df["base_weight"] * df["confidence"].fillna(0.6) * df["noise_weight"]

    total_weight = float(df["weight"].sum())
    sentiment_score = 0.0 if total_weight == 0 else float((df["score"] * df["weight"]).sum() / total_weight)

    message_volume = len(df)
    bullish_ratio = round((df["sentiment"] == "긍정").mean() * 100)
    bearish_ratio = round((df["sentiment"] == "부정").mean() * 100)
    neutral_ratio = max(0, 100 - bullish_ratio - bearish_ratio)

    avg_views = float(df["views"].mean()) if message_volume else 0
    total_engagement = int(df["likes"].sum() + df["dislikes"].sum())
    sentiment_polarization = abs(bullish_ratio - bearish_ratio)
    hype_index = min(100, round(message_volume * 1.1 + math.log1p(avg_views) * 7 + total_engagement * 0.18 + sentiment_polarization * 0.18))

    price_info = price_info or {"price": "-", "change": "-"}

    posts = df[
        [
            "title", "sentiment", "sentiment_code", "confidence", "reason", "is_noise",
            "views", "likes", "dislikes", "date", "source_page", "url",
        ]
    ].to_dict("records")

    return {
        "name": stock_name,
        "code": stock_code,
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
        "frequent_terms": extract_frequent_terms(df),
        "posts": posts,
        "raw_posts_df": df,
        "history_df": history_df if history_df is not None else pd.DataFrame(),
    }


def get_sentiment_label(score: float) -> str:
    if score >= 0.25:
        return "긍정 우세"
    if score <= -0.25:
        return "부정 우세"
    return "혼조/중립"


def build_market_interpretation(stock: dict[str, Any]) -> str:
    score = float(stock.get("sentiment_score", 0.0))
    hype = int(stock.get("hype_index", 0))
    bullish = int(stock.get("bullish_ratio", 0))
    bearish = int(stock.get("bearish_ratio", 0))
    history_df = stock.get("history_df", pd.DataFrame())

    price_context = "주가 흐름 데이터가 부족합니다."
    if isinstance(history_df, pd.DataFrame) and not history_df.empty:
        latest = history_df.iloc[-1]
        close = latest.get("close")
        ma20 = latest.get("ma20")
        ma60 = latest.get("ma60")

        if pd.notna(ma20) and pd.notna(close):
            if close > ma20:
                price_context = "현재 종가는 20일선 위에 있어 단기 추세는 비교적 양호합니다."
            else:
                price_context = "현재 종가는 20일선 아래에 있어 단기 추세 부담이 있습니다."

        if pd.notna(ma60) and pd.notna(close):
            if close > ma60:
                price_context += " 60일선 대비로도 중기 흐름은 버티는 편입니다."
            else:
                price_context += " 60일선 아래라 중기 흐름은 약한 편입니다."

    if score >= 0.25 and hype >= 70:
        sentiment_context = "커뮤니티 감성은 긍정 쪽으로 강하게 쏠려 있고 관심도도 높습니다. 추세 기대감 또는 과열 가능성을 함께 봐야 합니다."
    elif score >= 0.25:
        sentiment_context = "커뮤니티 감성은 긍정 우세입니다. 상승 기대 또는 저점 매수 심리가 나타납니다."
    elif score <= -0.25 and hype >= 70:
        sentiment_context = "커뮤니티 감성은 부정 우세이며 관심도도 높습니다. 악재, 고점 경계, 불안 심리가 확산되는 구간일 수 있습니다."
    elif score <= -0.25:
        sentiment_context = "커뮤니티 감성은 부정 우세입니다. 우려, 불만, 하락 경계성 글이 상대적으로 많습니다."
    else:
        sentiment_context = "커뮤니티 감성은 혼조입니다. 긍정/부정이 뚜렷하게 한쪽으로 쏠리지는 않았습니다."

    return f"{sentiment_context} 긍정 {bullish}%, 부정 {bearish}%입니다. {price_context}"

# ============================================================
# 5) 화면 렌더링 유틸
# ============================================================

def render_keyword_chips(keyword_dict: dict[str, int]) -> None:
    if not keyword_dict:
        st.caption("표시할 키워드가 충분하지 않습니다.")
        return

    max_weight = max(keyword_dict.values())
    html = "<div style='display:flex;flex-wrap:wrap;gap:8px;line-height:1.8;'>"
    for word, weight in sorted(keyword_dict.items(), key=lambda x: x[1], reverse=True):
        size = 13 + math.floor((weight / max_weight) * 11)
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


def keyword_dataframe(keyword_dict: dict[str, int], keyword_type: str) -> pd.DataFrame:
    if not keyword_dict:
        return pd.DataFrame(columns=["keyword", "weight", "type"])
    return pd.DataFrame(
        [{"keyword": key, "weight": value, "type": keyword_type} for key, value in keyword_dict.items()]
    ).sort_values("weight", ascending=False)


def find_stock_name(stock_code: str) -> str:
    return STOCK_PRESETS.get(stock_code, f"종목 {stock_code}")

# ============================================================
# 6) Sidebar
# ============================================================

with st.sidebar:
    st.header("📌 데이터 설정")

    stock_options = [f"{code} · {name}" for code, name in STOCK_PRESETS.items()]
    selected_option = st.selectbox("종목 선택", stock_options)
    selected_code = selected_option.split(" · ")[0]

    stock_code_input = st.text_input(
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
        help="1~N페이지를 실제로 수집합니다. 표의 수집 페이지는 해당 글의 출처 페이지입니다.",
    )

    chart_days = st.slider("주가 추이 일수", min_value=30, max_value=240, value=90, step=30)

    classification_mode = st.radio(
        "감성 분류 방식",
        options=["Rule", "LLM"],
        index=0,
        help="LLM은 OPENAI_API_KEY가 Render 환경변수에 있을 때만 작동합니다. 없으면 Rule로 자동 대체됩니다.",
    )

    llm_model_name = st.text_input("LLM 모델명", value="gpt-4o-mini")

    display_rows = st.slider("표시할 게시글 수", min_value=20, max_value=200, value=80, step=20)

    if st.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("수집 페이지 수가 10이면 1~10페이지를 실제 수집합니다.")
    st.caption("source_page는 글이 발견된 네이버 종목토론방 페이지 번호입니다.")

# ============================================================
# 7) 데이터 로딩
# ============================================================

stock_code = re.sub(r"\D", "", stock_code_input)[:6] or "005930"
stock_name = find_stock_name(stock_code)
data_source = "mock"
load_error = None

try:
    if use_live_data:
        with st.spinner("네이버 종목토론방과 주가 데이터를 수집하는 중입니다..."):
            live_posts_df = fetch_naver_board_pages(stock_code, page_count=page_count)
            price_info = fetch_naver_price_info(stock_code)
            history_df = fetch_naver_daily_prices(stock_code, count=chart_days)
            stock = build_stock_summary(
                stock_code=stock_code,
                stock_name=stock_name,
                posts_df=live_posts_df,
                price_info=price_info,
                history_df=history_df,
                classification_mode=classification_mode,
                llm_model_name=llm_model_name,
            )
            data_source = "live"
    else:
        stock = build_stock_summary(
            stock_code="005930",
            stock_name="삼성전자",
            posts_df=MOCK_POSTS,
            price_info={"price": "74,200", "change": "+900 / +1.23%"},
            history_df=MOCK_HISTORY,
            classification_mode="Rule",
            llm_model_name=llm_model_name,
        )
except Exception as exc:
    load_error = str(exc)
    stock = build_stock_summary(
        stock_code="005930",
        stock_name="삼성전자",
        posts_df=MOCK_POSTS,
        price_info={"price": "74,200", "change": "+900 / +1.23%"},
        history_df=MOCK_HISTORY,
        classification_mode="Rule",
        llm_model_name=llm_model_name,
    )

# ============================================================
# 8) Main layout
# ============================================================

st.title("📈 종목토론방 실시간 여론 대시보드")
st.caption("네이버 종목토론방 게시글과 주가 흐름을 함께 보며 커뮤니티 감성지수와 과열도를 추정합니다.")

if data_source == "live":
    st.success(f"실제 네이버 데이터를 수집했습니다. 수집 범위: 1~{page_count}페이지 · 수집 글 수: {stock['message_volume']:,}개")
elif load_error:
    st.warning(f"실제 데이터 수집에 실패해 mock 데이터로 표시합니다. 오류: {load_error}")
else:
    st.info("mock 데이터로 표시 중입니다.")

if classification_mode == "LLM" and not os.getenv("OPENAI_API_KEY"):
    st.warning("LLM 모드를 선택했지만 OPENAI_API_KEY가 없어 Rule 기반 분류로 자동 대체되었습니다.")

header_left, header_right = st.columns([2, 1])

with header_left:
    st.subheader(f"{stock['name']} · {stock['code']}")
    st.write(f"현재가 **{stock['price']}원** · 전일대비 **{stock['change']}** · 업데이트 **{stock['updated_at']}**")

with header_right:
    label = get_sentiment_label(stock["sentiment_score"])
    st.metric(
        label="오늘의 감성 상태",
        value=label,
        delta=f"감성 점수 {stock['sentiment_score']:+.2f}",
    )

st.info(build_market_interpretation(stock))

st.divider()

metric_cols = st.columns(4)
metric_cols[0].metric("긍정 비율", f"{stock['bullish_ratio']}%", f"부정 {stock['bearish_ratio']}%")
metric_cols[1].metric("게시글 수", f"{stock['message_volume']:,}", f"1~{page_count}페이지 기준" if data_source == "live" else "mock 기준")
metric_cols[2].metric("과열도", f"{stock['hype_index']}", "글 수·조회수·추천수·쏠림")
metric_cols[3].metric("감성 점수", f"{stock['sentiment_score']:+.2f}", "-1 부정 · 0 중립 · +1 긍정")

# ============================================================
# 9) Charts
# ============================================================

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
        for key, label_name in [("ma5", "5일선"), ("ma20", "20일선"), ("ma60", "60일선")]:
            if key in latest and pd.notna(latest[key]):
                ma_caption_parts.append(f"{label_name} {int(latest[key]):,}원")

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
            "ratio": [stock["bullish_ratio"], stock["bearish_ratio"], stock["neutral_ratio"]],
        }
    )
    st.bar_chart(ratio_df, x="sentiment", y="ratio")

chart_col_1, chart_col_2 = st.columns([1, 1])

with chart_col_1:
    st.subheader("키워드 가중치")
    keyword_df = pd.concat(
        [
            keyword_dataframe(stock["positive_keywords"], "긍정"),
            keyword_dataframe(stock["negative_keywords"], "부정"),
            keyword_dataframe(stock["frequent_terms"], "전체빈출"),
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

# ============================================================
# 10) Word clouds
# ============================================================

st.subheader("전체 빈출 어휘 워드클라우드")
render_keyword_chips(stock.get("frequent_terms", {}))
st.caption("감성 분류와 무관하게 전체 제목에서 자주 등장한 단어입니다. 시장 관심사와 이슈 파악용입니다.")

keyword_col_1, keyword_col_2 = st.columns(2)

with keyword_col_1:
    st.subheader("👍 긍정 키워드")
    render_keyword_chips(stock["positive_keywords"])

with keyword_col_2:
    st.subheader("👎 부정 키워드")
    render_keyword_chips(stock["negative_keywords"])

st.divider()

# ============================================================
# 11) Posts table
# ============================================================

st.subheader("최근 대표 글 제목")
st.caption(f"표의 수집 페이지는 해당 글이 발견된 네이버 종목토론방 페이지 번호입니다. 현재 화면은 최대 {display_rows}개 글을 보여줍니다.")

posts_df = pd.DataFrame(stock["posts"])
posts_df = posts_df.head(display_rows)

display_posts_df = posts_df.drop(columns=["url"], errors="ignore")

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
        "is_noise": "잡음 여부",
        "views": "조회",
        "likes": "추천",
        "dislikes": "비추천",
        "date": "작성일시",
        "source_page": "수집 페이지",
    },
)

if data_source == "live" and not posts_df.empty and "url" in posts_df.columns:
    with st.expander("게시글 링크 보기"):
        for _, row in posts_df.head(30).iterrows():
            if row.get("url"):
                st.markdown(f"- [{row['title']}]({row['url']})")

st.warning(
    "본 지표는 네이버 종목토론방 게시글 기반의 비정형 커뮤니티 감성 분석 결과이며, "
    "투자 권유나 매매 신호가 아닙니다."
)

# ============================================================
# 12) Guide
# ============================================================

with st.expander("현재 MVP 구조와 고도화 방향"):
    st.code(
        """
현재 버전:
1. 네이버 종목토론방 1~N페이지 수집
2. 한글 깨짐 방지: cp949/euc-kr 직접 디코딩
3. 제목을 해당 종목 관점에서 긍정/부정/중립 분류
   - 내부 코드: strong_bullish, weak_bullish, strong_bearish, weak_bearish, neutral_info, neutral_noise, neutral_chat
   - 화면 라벨: 긍정/부정/중립
   - 정치/잡담 noise는 감성 점수 가중치 낮춤
4. 전체 빈출 어휘 + 긍정 키워드 + 부정 키워드 표시
5. 네이버 일봉 차트에서 종가, 5/20/60일 이동평균선 표시
6. 감성 점수와 이평선 위치를 결합한 자동 해석 문구 제공

고도화 방향:
- LLM 모드 사용: Render 환경변수에 OPENAI_API_KEY 추가
- 본문까지 수집해 제목+본문 기반 분류
- SQLite/Postgres에 post_url 기준 중복 저장
- 1~5분마다 첫 페이지 누적 수집
- 시간대별 감성 변화 차트 추가
- 게시글 증가율, 거래량 증가율, 주가 변동률을 결합한 이상징후 지표 추가
        """,
        language="text",
    )

st.caption(f"마지막 화면 렌더링: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
