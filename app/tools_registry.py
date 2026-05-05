import json
from datetime import datetime
from .logger import logger
from .time_utils import local_now_naive
from .weather import get_weather


def _time_period_label(hour: int) -> str:
    if 0 <= hour < 5:
        return "凌晨"
    if 5 <= hour < 8:
        return "早上"
    if 8 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    return "晚上"


def _format_spoken_time(now: datetime) -> str:
    period = _time_period_label(now.hour)
    hour_12 = now.hour % 12 or 12
    return f"{period}{hour_12}点{now.minute:02d}分（{now.strftime('%H:%M')}）"


def build_current_time_reply(user_text: str = "") -> str:
    """构造确定性的当前本地时间回复，避免模型把 24 小时制猜错。"""
    now = local_now_naive()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    date_text = f"{now.year}年{now.month}月{now.day}日，{weekday}"
    time_text = _format_spoken_time(now)
    text = user_text or ""

    asks_date = any(marker in text for marker in ("几号", "几月几号", "日期", "今天"))
    asks_time = any(marker in text for marker in ("几点", "多少点", "什么时间", "当前时间", "几点钟"))

    if asks_date and not asks_time:
        fact = f"今天是{date_text}。"
    elif asks_date:
        fact = f"现在是{date_text}，{time_text}。"
    else:
        fact = f"现在是{time_text}。"
    return f"{fact}哼，手机不就在手边，还非要我报一遍。"

# --- 工具定义 (JSON Schema) ---
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的精确时间和日期，当用户询问现在几点、今天几号等时间问题时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定地区的实时天气和穿衣建议。如果用户询问某地的天气，调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "province": {
                        "type": "string",
                        "description": "省份名称，例如：广东、浙江。如果是直辖市，填城市名。",
                    },
                    "city": {"type": "string", "description": "城市名称，例如：深圳、杭州、北京。"},
                    "district": {
                        "type": "string",
                        "description": "区县名称，例如：南山、余杭、朝阳。若不需要可留空。",
                    },
                },
                "required": ["city"],
            },
        },
    },
]


# --- 工具执行路由 ---
def execute_tool(name: str, arguments_str: str) -> str:
    """
    根据工具名称和 JSON 参数执行对应的本地 Python 函数，返回字符串结果。
    """
    logger.info(f"🛠️ [Tool Calling] 尝试执行工具: {name}, 参数: {arguments_str}")
    try:
        args = json.loads(arguments_str) if arguments_str else {}
    except Exception as e:
        logger.error(f"❌ 工具参数解析失败: {e}")
        args = {}

    try:
        if name == "get_current_time":
            now = local_now_naive()
            tz_label = datetime.now().astimezone().tzname() or "本地时区"
            weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
            spoken_time = _format_spoken_time(now)
            return (
                f"当前服务器本地时间是：{now.strftime('%Y年%m月%d日 %H:%M:%S')} "
                f"{weekday}（{tz_label}）。回复用户时必须保留明确时段和 24 小时制，"
                f"例如：{spoken_time}。"
            )

        elif name == "get_weather":
            province = args.get("province", "")
            city = args.get("city", "未知城市")
            district = args.get("district", "")
            return get_weather(province=province, city=city, district=district)

        else:
            return f"找不到名为 {name} 的工具。"

    except Exception as e:
        logger.error(f"❌ 执行工具 {name} 异常: {e}")
        return f"执行工具时发生内部错误：{str(e)}"
