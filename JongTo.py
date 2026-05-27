import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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

STOPWORDS = {
    "그리고", "그러나", "그래서", "하지만", "오늘", "내일", "어제", "지금", "진짜", "정말",
    "너무", "매우", "계속", "그냥", "아직", "다시", "이번", "저번", "이제", "여기",
    "저기", "이거", "저거", "그거", "뭐냐", "뭔가", "때문", "대한", "관련", "종목",
    "주식", "주가", "시장", "사람", "개미", "님들", "형들", "ㅋㅋ", "ㅎㅎ", "ㅠㅠ",
    "있다", "없다", "한다", "된다", "같다", "보다", "하면", "해서", "하는", "이런",
    "저런", "그런", "아니", "하나", "이건", "이게", "그게", "ㅋㅋㅋ", "ㅎㅎㅎ",
    "삼성전자", "하이닉스", "네이버", "카카오", "현대차", "LG화학", "셀트리온",
    "입니다", "합니다", "하세요", "보세요", "있나요", "없나요", "어떻게", "얼마나",
}

# LLM 실패 시에만 사용하는 백업 룰
FALLBACK_POSITIVE_WORDS = [
    "상한가", "급등", "간다", "가즈아", "매수", "호재", "돌파", "신고가", "반등",
    "대박", "상승", "기대", "저평가", "수급", "실적", "목표가", "외국인", "기관",
    "강세", "회복", "성장", "수혜", "흑자", "계약", "수주", "좋다", "추세", "상방",
]

FALLBACK_NEGATIVE_WORDS = [
    "폭락", "하락", "손절", "물렸다", "물림", "악재", "끝났다", "망했다", "팔아라",
    "떡락", "하방", "실망", "폭망", "고점", "과열", "조정", "매도", "부진", "적자",
    "리스크", "불안", "급락", "던져", "털림", "횡보", "매물", "약세", "위험", "거품",
]

SENTIMENT_SCORE_MAP = {
    "bullish": 1.0,
    "bearish": -1.0,
    "neutral": 0.0,
    "sarcastic": -0.25,
    "spam": 0.0,
    "unknown": 0.0,
}

KOREAN_LABEL_MAP = {
    "bullish": "긍정",
    "bearish": "부정",
    "neutral": "중립",
    "sarcastic": "조롱/반어",
    "spam": "스팸",
    "unknown": "불확실",
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
    "sarcastic_ratio": 0,
    "spam_ratio": 0,
    "message_volume": 184,
    "hype_index": 76,
    "updated_at": "오늘 14:35",
    "top_keywords": [
        {
            "keyword": "외국인",
            "count": 12,
            "score": 92,
            "dominant_sentiment": "긍정",
            "bullish": 8,
            "bearish": 1,
            "neutral": 3,
            "sarcastic": 0,
            "spam": 0,
            "views": 1200,
            "likes": 32,
            "dislikes": 4,
        },
        {
            "keyword": "반등",
            "count": 9,
            "score": 78,
            "dominant_sentiment": "긍정",
            "bullish": 7,
            "bearish": 1,
            "neutral": 1,
            "sarcastic": 0,
            "spam": 0,
            "views": 900,
            "likes": 21,
            "dislikes": 2,
        },
    ],
    "posts": [
        {
            "title": "외국인 다시 들어오는 분위기네요",
            "sentiment": "긍정",
            "sentiment_code": "bullish",
            "confidence": 0.91,
            "reason": "수급 개선 기대가 드러남",
            "views": 482,
            "likes": 11,
            "dislikes": 2,
            "date": "-",
            "url": "",
            "page": 1,
        },
        {
            "title": "이걸 아직도 간다고 믿는 사람 있음?",
            "sentiment": "조롱/반어",
            "sentiment_code": "sarcastic",
            "confidence": 0.86,
            "reason": "상승 기대를 비꼬는 표현",
            "views": 298,
            "likes": 4,
            "dislikes": 7,
            "date": "-",
            "url": "",
            "page": 1,
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
            title = link_tag.get_text(" ", strip=True) if link_tag else cols[1]
            title = clean_title(title)

            if not title:
                continue

            post_url = ""
            if link_tag and link_tag.get("href"):
                post_url = "https://finance.naver.com" + link_tag["href"]

            rows.append(
                {
                    "date": date_text,
                    "title": title,
                    "author": cols[2] if len(cols) > 2 else "",
                    "views": to_int(cols[3] if len(cols) > 3 else "0"),
                    "likes": to_int(cols[4] if len(cols) > 4 else "0"),
                    "dislikes": to_int(cols[5] if len(cols) > 5 else "0"),
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
# 5) 문장/구 단위 LLM 감성분석
# ------------------------------------------------------------

def fallback_sentence_sentiment(title: str) -> dict[str, Any]:
    text = str(title)
    pos = sum(1 for word in FALLBACK_POSITIVE_WORDS if word in text)
    neg = sum(1 for word in FALLBACK_NEGATIVE_WORDS if word in text)

    if pos > neg:
        code = "bullish"
        reason = "백업 룰 기준 긍정 표현이 더 많음"
    elif neg > pos:
        code = "bearish"
        reason = "백업 룰 기준 부정 표현이 더 많음"
    else:
        code = "neutral"
        reason = "백업 룰 기준 방향성 불명확"

    return {
        "sentiment_code": code,
        "sentiment": KOREAN_LABEL_MAP[code],
        "confidence": 0.35,
        "reason": reason,
    }


def parse_response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "output_text") and response.output_text:
        return json.loads(response.output_text)

    texts = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                texts.append(text)

    if texts:
        return json.loads("\n".join(texts))

    raise ValueError("LLM 응답에서 JSON 텍스트를 찾지 못했습니다.")


def classify_sentence_batch_with_llm(
    batch_items: list[dict[str, Any]],
    stock_name: str,
    model: str,
) -> list[dict[str, Any]]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "integer"},
                        "sentiment": {
                            "type": "string",
                            "enum": [
                                "bullish",
                                "bearish",
                                "neutral",
                                "sarcastic",
                                "spam",
                                "unknown",
                            ],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {
                            "type": "string",
                        },
                    },
                    "required": ["id", "sentiment", "confidence", "reason"],
                },
            }
        },
        "required": ["items"],
    }

    system_prompt = """
너는 한국 주식 종목토론방 게시글 제목을 분석하는 금융 커뮤니티 감성 분류기다.

가장 중요한 원칙:
- 단어 하나만 보고 판단하지 마라.
- 제목 전체 문장 또는 구의 의미, 말투, 반어법, 비꼼, 맥락을 기준으로 판단해라.
- 예를 들어 '간다'라는 단어가 있어도 비꼼이면 긍정이 아니다.
- 예를 들어 '손절'이라는 단어가 있어도 전체 문장이 회복 기대면 단순 부정이 아닐 수 있다.

분류 기준:
- bullish: 주가 상승 기대, 매수 심리, 호재 반응, 수급 개선 기대, 긍정적 전망
- bearish: 주가 하락 우려, 매도 심리, 악재 반응, 손절/탈출/고점 경고, 부정적 전망
- neutral: 단순 질문, 정보 공유, 방향성 없는 관망, 감성이 약한 글
- sarcastic: 반어법, 조롱, 비꼼, 비관적 농담. 투자심리상 약한 부정으로 본다.
- spam: 광고, 리딩방, 도배, 종목과 무관한 글
- unknown: 의미를 판단하기 어려운 글

출력:
- 입력 id마다 반드시 하나씩 결과를 반환해라.
- reason은 한국어로 짧게 작성해라.
"""

    user_payload = {
        "stock_name": stock_name,
        "items": batch_items,
    }

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "다음 게시글 제목들을 제목 전체 문장/구 단위로 감성 분류해줘.\n"
                    f"{json.dumps(user_payload, ensure_ascii=False)}"
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "stock_board_sentence_sentiment",
                "strict": True,
                "schema": schema,
            }
        },
        temperature=0,
    )

    parsed = parse_response_json(response)
    return parsed.get("items", [])


@st.cache_data(ttl=900, show_spinner=False)
def classify_titles_cached(
    titles: tuple[str, ...],
    stock_name: str,
    model: str,
    batch_size: int,
    max_workers: int,
    use_llm: bool,
) -> list[dict[str, Any]]:
    title_items = [{"id": idx, "title": title} for idx, title in enumerate(titles)]

    if not use_llm or not OPENAI_API_KEY:
        return [
            {"id": item["id"], **fallback_sentence_sentiment(item["title"])}
            for item in title_items
        ]

    batches = [
        title_items[i : i + batch_size]
        for i in range(0, len(title_items), batch_size)
    ]

    results: list[dict[str, Any]] = []

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    classify_sentence_batch_with_llm,
                    batch,
                    stock_name,
                    model,
                ): batch
                for batch in batches
            }

            for future in as_completed(future_map):
                batch = future_map[future]
                try:
                    results.extend(future.result())
                except Exception:
                    for item in batch:
                        results.append(
                            {
                                "id": item["id"],
                                **fallback_sentence_sentiment(item["title"]),
                            }
                        )

    except Exception:
        results = [
            {"id": item["id"], **fallback_sentence_sentiment(item["title"])}
            for item in title_items
        ]

    by_id = {int(item["id"]): item for item in results if "id" in item}

    normalized = []
    for item in title_items:
        idx = item["id"]
        result = by_id.get(idx)

        if not result:
            result = {"id": idx, **fallback_sentence_sentiment(item["title"])}

        code = result.get("sentiment", result.get("sentiment_code", "unknown"))
        if code not in SENTIMENT_SCORE_MAP:
            code = "unknown"

        try:
            confidence = float(result.get("confidence", 0.5))
        except Exception:
            confidence = 0.5

        confidence = min(max(confidence, 0.0), 1.0)

        normalized.append(
            {
                "id": idx,
                "sentiment_code": code,
                "sentiment": KOREAN_LABEL_MAP.get(code, "불확실"),
                "confidence": confidence,
                "reason": str(result.get("reason", ""))[:100],
            }
        )

    return sorted(normalized, key=lambda x: x["id"])


def attach_sentence_sentiment(
    posts_df: pd.DataFrame,
    stock_name: str,
    model: str,
    batch_size: int,
    max_workers: int,
    use_llm: bool,
) -> pd.DataFrame:
    df = posts_df.copy().reset_index(drop=True)
    titles = tuple(df["title"].astype(str).tolist())

    classifications = classify_titles_cached(
        titles=titles,
        stock_name=stock_name,
        model=model,
        batch_size=batch_size,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    class_df = pd.DataFrame(classifications)

    df = df.reset_index().rename(columns={"index": "id"})
    df = df.merge(class_df, on="id", how="left")

    df["sentiment_code"] = df["sentiment_code"].fillna("unknown")
    df["sentiment"] = df["sentiment"].fillna("불확실")
    df["confidence"] = df["confidence"].fillna(0.3)
    df["reason"] = df["reason"].fillna("분류 실패")
    df["sentiment_value"] = df["sentiment_code"].map(SENTIMENT_SCORE_MAP).fillna(0.0)

    return df.drop(columns=["id"])


# ------------------------------------------------------------
# 6) 빈출 키워드 추출 및 키워드 문맥 감성 집계
# ------------------------------------------------------------

def tokenize_korean_title(text: str) -> list[str]:
    text = clean_text(text)
    candidates = re.findall(r"[가-힣A-Za-z0-9]{2,}", text)

    tokens = []
    for token in candidates:
        token = token.strip()

        if len(token) < 2:
            continue

        if token in STOPWORDS:
            continue

        if token.isdigit:
            pass

        if token.isdigit():
            continue

        if token.endswith(("네요", "합니다", "는데", "듯요", "인가", "이냐", "냐고")) and len(token) <= 4:
            continue

        tokens.append(token)

    return tokens


def extract_contextual_keywords(posts_df: pd.DataFrame, top_n: int = 25) -> list[dict[str, Any]]:
    """
    키워드 자체를 긍정/부정으로 판단하지 않습니다.
    해당 키워드가 포함된 제목들의 LLM 감성 결과를 집계해서 키워드의 문맥상 주요 감성을 계산합니다.
    """
    if posts_df.empty:
        return []

    keyword_counter = Counter()
    view_counter = Counter()
    like_counter = Counter()
    dislike_counter = Counter()
    sentiment_counter: dict[str, Counter] = defaultdict(Counter)

    for _, row in posts_df.iterrows():
        title = str(row.get("title", ""))
        tokens = set(tokenize_korean_title(title))

        sentiment_code = str(row.get("sentiment_code", "unknown"))
        views = int(row.get("views", 0) or 0)
        likes = int(row.get("likes", 0) or 0)
        dislikes = int(row.get("dislikes", 0) or 0)

        for token in tokens:
            keyword_counter[token] += 1
            view_counter[token] += views
            like_counter[token] += likes
            dislike_counter[token] += dislikes
            sentiment_counter[token][sentiment_code] += 1

    results = []

    for keyword, count in keyword_counter.items():
        views = view_counter[keyword]
        likes = like_counter[keyword]
        dislikes = dislike_counter[keyword]
        sentiment_counts = sentiment_counter[keyword]

        dominant_code = sentiment_counts.most_common(1)[0][0]
        dominant_sentiment = KOREAN_LABEL_MAP.get(dominant_code, "불확실")

        bullish = sentiment_counts.get("bullish", 0)
        bearish = sentiment_counts.get("bearish", 0)
        neutral = sentiment_counts.get("neutral", 0)
        sarcastic = sentiment_counts.get("sarcastic", 0)
        spam = sentiment_counts.get("spam", 0)
        unknown = sentiment_counts.get("unknown", 0)

        context_score = (
            bullish * 1.0
            + bearish * -1.0
            + sarcastic * -0.25
        )

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
                "dominant_sentiment": dominant_sentiment,
                "context_score": round(context_score, 2),
                "bullish": int(bullish),
                "bearish": int(bearish),
                "neutral": int(neutral),
                "sarcastic": int(sarcastic),
                "spam": int(spam),
                "unknown": int(unknown),
                "views": int(views),
                "likes": int(likes),
                "dislikes": int(dislikes),
            }
        )

    results = sorted(results, key=lambda x: (x["count"], x["score"]), reverse=True)
    return results[:top_n]


# ------------------------------------------------------------
# 7) 지표 집계
# ------------------------------------------------------------

def build_stock_summary(
    stock_code: str,
    stock_name: str,
    price_info: dict[str, str],
    posts_df: pd.DataFrame,
    model: str,
    batch_size: int,
    max_workers: int,
    use_llm: bool,
) -> dict[str, Any]:
    if posts_df.empty:
        raise ValueError("수집된 게시글이 없습니다.")

    df = attach_sentence_sentiment(
        posts_df=posts_df,
        stock_name=stock_name,
        model=model,
        batch_size=batch_size,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    df["weight"] = (
        1
        + df["views"].fillna(0).apply(lambda x: math.log1p(max(x, 0)))
        + df["likes"].fillna(0) * 0.15
        - df["dislikes"].fillna(0) * 0.08
    ).clip(lower=0.2)

    df["confidence_weight"] = df["weight"] * df["confidence"].fillna(0.5)

    total_weight = df["confidence_weight"].sum()

    if total_weight == 0:
        sentiment_score = 0.0
    else:
        sentiment_score = float(
            (df["sentiment_value"] * df["confidence_weight"]).sum() / total_weight
        )

    message_volume = len(df)

    bullish_ratio = round((df["sentiment_code"] == "bullish").mean() * 100)
    bearish_ratio = round((df["sentiment_code"] == "bearish").mean() * 100)
    sarcastic_ratio = round((df["sentiment_code"] == "sarcastic").mean() * 100)
    spam_ratio = round((df["sentiment_code"] == "spam").mean() * 100)
    unknown_ratio = round((df["sentiment_code"] == "unknown").mean() * 100)

    neutral_ratio = max(
        0,
        100 - bullish_ratio - bearish_ratio - sarcastic_ratio - spam_ratio - unknown_ratio,
    )

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

    top_keywords = extract_contextual_keywords(df, top_n=25)

    posts = df[
        [
            "title",
            "sentiment",
            "sentiment_code",
            "confidence",
            "reason",
            "views",
            "likes",
            "dislikes",
            "date",
            "url",
            "page",
        ]
    ].head(80).to_dict("records")

    return {
        "name": price_info.get("name") or stock_name,
        "price": price_info.get("price", "-"),
        "change": price_info.get("change", "-"),
        "change_text": price_info.get("change_text", "-"),
        "sentiment_score": sentiment_score,
        "bullish_ratio": bullish_ratio,
        "bearish_ratio": bearish_ratio,
        "neutral_ratio": neutral_ratio,
        "sarcastic_ratio": sarcastic_ratio,
        "spam_ratio": spam_ratio,
        "unknown_ratio": unknown_ratio,
        "message_volume": message_volume,
        "hype_index": hype_index,
        "updated_at": datetime.now().strftime("%H:%M"),
        "top_keywords": top_keywords,
        "posts": posts,
        "raw_posts_df": df,
    }


def get_sentiment_label(score: float) -> str:
    if score >= 0.25:
        return "긍정 우세"
    if score <= -0.25:
        return "부정 우세"
    return "중립"


def keyword_dataframe(top_keywords: list[dict[str, Any]]) -> pd.DataFrame:
    if not top_keywords:
        return pd.DataFrame(
            columns=[
                "keyword",
                "count",
                "score",
                "dominant_sentiment",
                "context_score",
                "bullish",
                "bearish",
                "neutral",
                "sarcastic",
                "spam",
                "views",
                "likes",
                "dislikes",
            ]
        )

    return pd.DataFrame(top_keywords)


def render_keyword_chips(top_keywords: list[dict[str, Any]]) -> None:
    if not top_keywords:
        st.caption("아직 충분한 키워드가 감지되지 않았습니다.")
        return

    max_score = max(float(item["score"]) for item in top_keywords) or 1
    html = "<div style='display:flex;flex-wrap:wrap;gap:8px;'>"

    for item in top_keywords[:25]:
        keyword = item["keyword"]
        score = float(item["score"])
        sentiment = item["dominant_sentiment"]
        count = item["count"]

        size = 13 + math.floor((score / max_score) * 10)

        if sentiment == "긍정":
            bg = "#dcfce7"
            color = "#166534"
        elif sentiment in ["부정", "조롱/반어"]:
            bg = "#fee2e2"
            color = "#991b1b"
        elif sentiment == "스팸":
            bg = "#f3f4f6"
            color = "#6b7280"
        else:
            bg = "#f1f5f9"
            color = "#334155"

        html += (
            f"<span title='빈도 {count}회 / 점수 {score} / 주요 감성 {sentiment}' "
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
    use_llm = st.toggle("OpenAI 문장/구 단위 감성분석 사용", value=True)

    st.caption(f"LLM 모델: {OPENAI_MODEL}")

    batch_size = st.slider(
        "LLM 배치 크기",
        min_value=10,
        max_value=40,
        value=25,
        step=5,
        help="한 번의 API 호출에 넣을 제목 수입니다.",
    )

    max_workers = st.slider(
        "LLM 병렬 요청 수",
        min_value=1,
        max_value=6,
        value=3,
        step=1,
        help="너무 높이면 API rate limit에 걸릴 수 있습니다.",
    )

    if st.button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("현재가와 등락률은 네이버 금융 종목 메인에서 가져옵니다.")
    st.caption("감성은 게시글 제목 전체 문장/구 단위로 분류합니다.")
    st.caption("키워드는 빈출 단어를 뽑고, 해당 키워드가 포함된 문장들의 LLM 감성을 집계합니다.")
    st.caption("LLM 실패 시 백업 룰 기반 감성분석으로 자동 전환됩니다.")

# ------------------------------------------------------------
# 9) 데이터 로딩
# ------------------------------------------------------------

stock_code = re.sub(r"\D", "", stock_code)[:6] or "005930"
stock_name = find_stock_name(stock_code)

data_source = "mock"
load_error = None
llm_status = "미사용"

if use_live_data:
    try:
        price_info = fetch_stock_price(stock_code)
        live_posts_df = fetch_naver_board_pages(stock_code, max_pages=max_pages)

        if use_llm and OPENAI_API_KEY:
            llm_status = f"OpenAI 문장/구 단위 분석 사용: {OPENAI_MODEL}"
        elif use_llm and not OPENAI_API_KEY:
            llm_status = "OPENAI_API_KEY 없음 → 백업 룰 사용"
        else:
            llm_status = "백업 룰 사용"

        stock = build_stock_summary(
            stock_code=stock_code,
            stock_name=stock_name,
            price_info=price_info,
            posts_df=live_posts_df,
            model=OPENAI_MODEL,
            batch_size=batch_size,
            max_workers=max_workers,
            use_llm=use_llm,
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
    "네이버 종목토론방의 최신 게시글 제목을 문장/구 단위로 분석해 "
    "현재가, 등락률, 커뮤니티 감성지수, 문맥 기반 키워드 감성을 보여줍니다."
)

if data_source == "live":
    st.success(
        f"실제 네이버 데이터를 수집해 표시 중입니다. "
        f"종목토론방 {max_pages}페이지 기준 · {llm_status}"
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
    "문장 기반 감성 점수",
    f"{stock['sentiment_score']:+.2f}",
    "-1 ~ +1",
)

detail_cols = st.columns(4)

detail_cols[0].metric("중립 비율", f"{stock.get('neutral_ratio', 0)}%")
detail_cols[1].metric("조롱/반어 비율", f"{stock.get('sarcastic_ratio', 0)}%")
detail_cols[2].metric("스팸 비율", f"{stock.get('spam_ratio', 0)}%")
detail_cols[3].metric("불확실 비율", f"{stock.get('unknown_ratio', 0)}%")

# ------------------------------------------------------------
# 11) 차트
# ------------------------------------------------------------

chart_col_1, chart_col_2 = st.columns([1, 1])

with chart_col_1:
    st.subheader("문장/구 단위 감성 비율")

    ratio_df = pd.DataFrame(
        {
            "sentiment": ["긍정", "부정", "중립", "조롱/반어", "스팸", "불확실"],
            "ratio": [
                stock.get("bullish_ratio", 0),
                stock.get("bearish_ratio", 0),
                stock.get("neutral_ratio", 0),
                stock.get("sarcastic_ratio", 0),
                stock.get("spam_ratio", 0),
                stock.get("unknown_ratio", 0),
            ],
        }
    )

    st.bar_chart(ratio_df, x="sentiment", y="ratio")

with chart_col_2:
    st.subheader("문맥 기반 빈출 키워드 랭킹")

    keyword_df = keyword_dataframe(stock.get("top_keywords", []))

    st.dataframe(
        keyword_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "keyword": "키워드",
            "count": "빈도",
            "score": "가중치",
            "dominant_sentiment": "주요 문맥 감성",
            "context_score": "문맥 점수",
            "bullish": "긍정 문장",
            "bearish": "부정 문장",
            "neutral": "중립 문장",
            "sarcastic": "조롱/반어 문장",
            "spam": "스팸 문장",
            "unknown": "불확실 문장",
            "views": "조회 합",
            "likes": "추천 합",
            "dislikes": "비추천 합",
        },
    )

st.subheader("문맥 기반 키워드 클라우드")
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
        "sentiment": "문장 감성",
        "sentiment_code": "감성 코드",
        "confidence": "신뢰도",
        "reason": "LLM 판단 근거",
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
3. 게시글 제목 전체를 문장/구 단위로 OpenAI LLM 감성분석
4. 여러 배치를 병렬 처리해 지연시간 감소
5. 감성 라벨: 긍정 / 부정 / 중립 / 조롱·반어 / 스팸 / 불확실
6. 실제 제목에서 빈출 키워드 추출
7. 키워드 자체를 긍정/부정으로 고정하지 않고,
   해당 키워드가 포함된 문장들의 LLM 감성을 집계
8. 조회수·추천수·비추천수·LLM 신뢰도로 최종 감성 점수와 과열도 계산

환경변수:
- OPENAI_API_KEY
- OPENAI_MODEL, 기본값 gpt-4.1-mini

권장 설정:
- 수집 페이지 수: 2~3
- LLM 배치 크기: 25
- LLM 병렬 요청 수: 2~3

주의:
- 병렬 요청 수를 과도하게 높이면 rate limit에 걸릴 수 있습니다.
- 실제 서비스에서는 주기적 수집 + DB 누적 방식이 더 안정적입니다.
        """,
        language="text",
    )

st.caption(f"마지막 화면 렌더링: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
