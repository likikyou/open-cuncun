"""
天气模块 - 使用 Open-Meteo 免费 API（无需 Key）
获取指定地区的实时天气信息
"""

import os
import requests
from typing import Tuple
from .logger import logger

# WMO 天气代码 → 中文描述
WMO_WEATHER_CODES = {
    0: "晴天 ☀️",
    1: "基本晴朗 🌤️",
    2: "多云 ⛅",
    3: "阴天 ☁️",
    45: "雾 🌫️",
    48: "雾凇 🌫️",
    51: "小毛毛雨 🌦️",
    53: "中毛毛雨 🌧️",
    55: "大毛毛雨 🌧️",
    61: "小雨 🌧️",
    63: "中雨 🌧️",
    65: "大雨 🌧️",
    66: "冻雨（小）❄️🌧️",
    67: "冻雨（大）❄️🌧️",
    71: "小雪 🌨️",
    73: "中雪 🌨️",
    75: "大雪 🌨️",
    77: "雪粒 ❄️",
    80: "阵雨（小）🌦️",
    81: "阵雨（中）🌧️",
    82: "阵雨（大）⛈️",
    85: "阵雪（小）🌨️",
    86: "阵雪（大）🌨️",
    95: "雷阵雨 ⛈️",
    96: "雷阵雨+小冰雹 ⛈️",
    99: "雷阵雨+大冰雹 ⛈️",
}

# 默认经纬度 (可通过环境变量配置)
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "39.90"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "116.41"))

# 常用城市经纬度预置映射（覆盖省会 + 热门城市，避免依赖外部地理编码服务）
_CITY_COORDS = {
    "北京": (39.90, 116.41),
    "上海": (31.23, 121.47),
    "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06),
    "杭州": (30.27, 120.15),
    "南京": (32.06, 118.80),
    "成都": (30.57, 104.07),
    "重庆": (29.56, 106.55),
    "武汉": (30.59, 114.30),
    "西安": (34.26, 108.94),
    "长沙": (28.23, 112.94),
    "天津": (39.13, 117.20),
    "苏州": (31.30, 120.62),
    "郑州": (34.75, 113.65),
    "青岛": (36.07, 120.38),
    "大连": (38.91, 121.60),
    "厦门": (24.48, 118.09),
    "济南": (36.65, 116.99),
    "福州": (26.07, 119.30),
    "合肥": (31.82, 117.23),
    "昆明": (25.04, 102.71),
    "贵阳": (26.65, 106.63),
    "南昌": (28.68, 115.89),
    "哈尔滨": (45.75, 126.65),
    "沈阳": (41.81, 123.43),
    "长春": (43.88, 125.32),
    "南宁": (22.82, 108.37),
}


def _get_coords(city: str) -> Tuple[float, float]:
    """根据城市名查找坐标，未命中返回默认值"""
    return _CITY_COORDS.get(city, (DEFAULT_LAT, DEFAULT_LON))


def get_weather(province: str = None, city: str = None, district: str = None) -> str:
    """
    获取指定地区的实时天气（使用 Open-Meteo 免费 API）
    返回格式化的中文天气描述
    """
    if province is None:
        province = os.getenv("DEFAULT_WEATHER_PROVINCE", "北京")
    if city is None:
        city = os.getenv("DEFAULT_WEATHER_CITY", "北京")
    if district is None:
        district = os.getenv("DEFAULT_WEATHER_DISTRICT", "北京")
    try:
        # 级联查找坐标：区县 → 城市 → 默认值
        if district and district in _CITY_COORDS:
            lat, lon = _CITY_COORDS[district]
        else:
            lat, lon = _get_coords(city)

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "timezone": "Asia/Shanghai",
        }

        # 使用原生 requests 进行请求，避免发送飞书 Token
        resp = requests.get(url, params=params, timeout=10)

        if resp and resp.status_code == 200:
            data = resp.json().get("current")
            if not data:
                raise ValueError("API 返回数据为空")

            temp = data.get("temperature_2m", "?")
            feel = data.get("apparent_temperature", "?")
            humidity = data.get("relative_humidity_2m", "?")
            wind = data.get("wind_speed_10m", "?")
            code = data.get("weather_code", -1)
            weather_desc = WMO_WEATHER_CODES.get(code, f"天气代码{code}")

            result = (
                f"{province}{city}{district}实时天气：{weather_desc}，"
                f"气温 {temp}°C，体感 {feel}°C，"
                f"湿度 {humidity}%，风速 {wind}km/h"
            )

            # 添加穿衣建议
            try:
                t = float(temp)
                if t < 5:
                    result += "。🧣 天冷，注意多穿衣服保暖！"
                elif t < 15:
                    result += "。🧥 温度偏低，记得加件外套。"
                elif t < 25:
                    result += "。👕 温度舒适，适合出门活动。"
                else:
                    result += "。🌞 天热，记得防晒多喝水！"
            except (ValueError, TypeError):
                pass

            return result
        else:
            logger.warning(f"天气 API 请求失败: {resp.status_code if resp else 'No Response'}")

    except Exception as e:
        logger.error(f"天气获取失败: {e}")

    return f"{province}{city}{district} 天气获取稍有延迟，记得多关注天气预报喔。"
