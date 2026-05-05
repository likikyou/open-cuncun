"""
联网搜索模块
使用博查 API 进行网络搜索
"""

from cachetools import TTLCache
from .config import Config
from .domain.query_intent import is_weather_query, normalize_weather_query
from .logger import logger
from .http_client import http_session
from .time_utils import local_now_naive


_search_cache = TTLCache(maxsize=100, ttl=3600)

_FRESHNESS_MARKERS = [
    "最新",
    "新出",
    "新上映",
    "刚上映",
    "正在上映",
    "热映",
    "上映电影",
    "院线电影",
    "五一档",
    "春节档",
    "暑期档",
    "国庆档",
    "票房",
    "榜单",
]

_MOVIE_TERMS = ("电影", "影片", "院线", "新片", "片单", "恐怖片", "动画片")
_MOVIE_QUESTION_MARKERS = (
    "哪些",
    "什么",
    "有啥",
    "有什么",
    "推荐",
    "上映",
    "热映",
    "票房",
    "片单",
    "档",
)


class SearchUnavailableError(RuntimeError):
    """联网搜索不可用时抛出，交给上层显式打标。"""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        severity: str = "warning",
        **details,
    ) -> None:
        super().__init__(message)
        self.degradation_component = "search"
        self.degradation_reason = reason
        self.degradation_severity = severity
        self.degradation_details = details


def _response_preview(text: str, limit: int = 200) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _is_movie_search_query(text: str) -> bool:
    has_movie_term = any(term in text for term in _MOVIE_TERMS)
    if not has_movie_term:
        return False
    if any(marker in text for marker in _FRESHNESS_MARKERS):
        return True
    has_question = "?" in text or "？" in text or "吗" in text or "啊" in text
    return has_question and any(marker in text for marker in _MOVIE_QUESTION_MARKERS)


def normalize_search_query(query: str) -> str:
    """把口语问句改写成更适合搜索引擎的关键词。"""
    raw_query = (query or "").strip()
    if not raw_query:
        return ""

    weather_query = normalize_weather_query(raw_query)
    if is_weather_query(weather_query):
        return weather_query

    text = raw_query
    for token in ("你知道", "知道"):
        text = text.replace(token, "")
    text = text.strip(" ，,。？！?!啊呢吗")

    if _is_movie_search_query(raw_query):
        now = local_now_naive()
        parts = [f"{now.year}年{now.month}月", "中国大陆", "院线", "正在上映", "最新电影"]
        if "五一" in raw_query or (now.month == 5 and now.day <= 7):
            parts.append("五一档")
        if "恐怖" in raw_query:
            parts.append("国产恐怖片")
        parts.append("片单")
        return " ".join(dict.fromkeys(parts))

    return text or raw_query


def _search_freshness(query: str) -> str:
    if _is_movie_search_query(query):
        return "oneMonth"
    if any(marker in query for marker in _FRESHNESS_MARKERS):
        return "oneMonth"
    return "noLimit"


def search_web_bocha(query: str, count: int = 5) -> str:
    raw_query = (query or "").strip()
    freshness = _search_freshness(raw_query)
    query = normalize_search_query(raw_query)
    query = (query or "").strip()
    if not query:
        return ""

    api_key = Config.BOCHA_API_KEY
    if not api_key:
        raise SearchUnavailableError(
            "bocha_api_key_missing",
            "BOCHA_API_KEY 未配置，联网搜索不可用",
            severity="error",
            query=query,
        )

    if query in _search_cache:
        logger.info(f"⚡ 联网搜索缓存命中: {query}")
        return _search_cache[query]

    url = "https://api.bocha.cn/v1/web-search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"query": query, "summary": True, "freshness": freshness, "count": count}

    try:
        resp = http_session.post(url, headers=headers, json=payload, timeout=10)
    except Exception as exc:
        raise SearchUnavailableError(
            "bocha_request_failed",
            f"博查搜索请求异常: {exc}",
            query=query,
            error_type=exc.__class__.__name__,
        ) from exc

    if resp.status_code != 200:
        raise SearchUnavailableError(
            "bocha_http_error",
            f"博查搜索 HTTP 失败: {resp.status_code}",
            query=query,
            status_code=resp.status_code,
            response_preview=_response_preview(resp.text),
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise SearchUnavailableError(
            "bocha_invalid_json",
            f"博查搜索返回非 JSON: {exc}",
            query=query,
            error_type=exc.__class__.__name__,
            response_preview=_response_preview(resp.text),
        ) from exc

    if not (data.get("code") == 200 or data.get("status") == "success"):
        raise SearchUnavailableError(
            "bocha_business_error",
            f"博查搜索业务失败: code={data.get('code')} status={data.get('status')}",
            query=query,
            api_code=data.get("code"),
            api_status=data.get("status"),
            api_message=data.get("message") or data.get("msg"),
        )

    results = data.get("data", {}).get("webPages", {}).get("value", [])
    if not results:
        results = data.get("webPages", {}).get("value", [])

    info_list = []
    for res in results[:count]:
        title = res.get("name") or res.get("title")
        summary = res.get("summary") or res.get("snippet")
        if summary:
            info_list.append(f"【{title}】: {summary}")

    if info_list:
        result = "\n".join(info_list)
        logger.info(
            f"🌐 博查搜索命中: {query}",
            extra={"raw_query": raw_query, "freshness": freshness},
        )
        _search_cache[query] = result
        return result

    logger.info(f"🌐 博查搜索无结果: {query}", extra={"raw_query": raw_query})
    return ""


def should_search(user_text: str) -> bool:
    text = user_text or ""
    strong_keywords = ["天气", "新闻", "多少钱", "价格", "怎么去", "在哪里", "地址", "什么时候"]
    if any(kw in text for kw in strong_keywords):
        return True

    time_words = ["今天", "明天", "昨天", "最近", "现在", "这周", "下周", "最新", "新出"]
    question_words = ["什么", "谁", "哪", "怎么", "多少", "几", "吗"]
    has_time = any(tw in text for tw in time_words)
    has_question = (
        "?" in text or "？" in text or any(q in text for q in question_words)
    )
    if has_question and any(marker in text for marker in _FRESHNESS_MARKERS):
        return True
    if _is_movie_search_query(text):
        return True

    return has_time and has_question and len(text) > 5
