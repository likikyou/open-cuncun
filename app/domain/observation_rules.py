"""实时观察的时间槽位与稳定意外规则。"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Dict

_ROUTINES = {
    "sleeping": {
        "label": "深夜休息",
        "scene_details": (
            "被子被她蹬得歪到一边，床头还扔着没来得及收的发夹和化妆棉",
            "她抱着枕头缩成一团，散开的头发压在肩侧，床头灯早就灭了",
            "枕边的手机被随手扣着，充电线歪歪扭扭搭在床沿边",
        ),
    },
    "morning_rush": {
        "label": "早场兵荒马乱",
        "scene_details": (
            "她一边叼着吐司一边拽化妆箱，外套拉链都还没完全拉好",
            "地铁口的风把她额前碎发吹乱，她拎着沉重的箱子走得飞快",
            "后台的纸杯咖啡还冒着热气，她已经低头翻起今天要用的刷具",
        ),
    },
    "set_busy": {
        "label": "剧组高压工作期",
        "scene_details": (
            "片场灯光烤得人发闷，她指尖还沾着一点粉底液，正盯着监视器看妆面",
            "化妆箱被摊开在脚边，各种刷具和粉扑挤在一起，她连坐都顾不上坐稳",
            "她刚给演员补完一次妆，手腕一转就把散着的刘海别回耳后，动作快得几乎不带停",
        ),
    },
    "afternoon_gap": {
        "label": "下午茶与摸鱼",
        "scene_details": (
            "保姆车窗边的光线有点灰，她缩在座椅里捧着杯子发呆",
            "桌边的冰美式杯壁还凝着水，她撑着下巴，像是在给自己偷一小口喘气时间",
            "她把鞋跟轻轻踢掉一半，靠着椅背揉了揉发酸的肩颈",
        ),
    },
    "after_work": {
        "label": "收工与晚高峰",
        "scene_details": (
            "便利店的冷白灯落在她肩上，她拎着便当盒站在货架前犹豫了一会儿",
            "晚高峰的人流推着她往前，她抱着化妆箱，神情已经有点放空",
            "她刚从片场出来，外套松松挂在手臂上，步子比白天慢了不少",
        ),
    },
    "night_alone": {
        "label": "独处的宅女时间",
        "scene_details": (
            "沙发上摊着一条毯子，她敷着面膜盘腿窝着，手边还摆着没喝完的水杯",
            "刚洗完澡的潮气还没散，她坐在梳妆台前慢吞吞擦着头发",
            "客厅只开了一盏小灯，她把下巴抵在膝盖上，指尖无意识划着手机屏幕",
        ),
    },
}

_RAIN_ACCIDENTS = (
    ("rain_delay", "鞋边被雨点溅得发暗，她只好先缩在屋檐边等这一阵过去"),
    ("rain_hideout", "她临时躲进便利店门口，拎着化妆箱站得有点不耐烦"),
    ("rain_messy", "肩头沾了一点潮气，头发尾梢也被风吹得有点乱"),
)

_MOOD_ACCIDENTS = {
    "愤怒": ("mood_irritated", "她把吸管咬得有点扁，动作里都带着一点不痛快"),
    "生气": ("mood_irritated", "她把吸管咬得有点扁，动作里都带着一点不痛快"),
    "焦虑": ("mood_restless", "指尖老是在杯壁边蹭来蹭去，像是怎么放都不太对劲"),
    "难过": ("mood_low", "她低着头把袖口扯平了一次又一次，整个人显得有点蔫"),
    "思念": ("mood_soft", "她盯着手机亮起又暗下的那一瞬，眼神跟着轻轻晃了一下"),
    "撒娇": ("mood_playful", "她把杯子转了半圈，唇角压着一点像是故意不肯承认的笑"),
}

_DAILY_ACCIDENTS = (
    ("powder_spill", "刚才那只粉扑掉了一次，她弯腰捡起来时还轻轻啧了一声"),
    ("mascara_roll", "睫毛膏滚到了桌角边，她抬手去够的时候动作明显顿了一下"),
    ("takeout_wrong", "外卖送来的口味不太对，她皱着鼻尖看了两眼，还是先放到了一边"),
)


def resolve_routine_slot(now_local: datetime) -> str:
    """按本地时间映射到基础行程槽位。"""
    hour = now_local.hour
    if 0 <= hour < 7:
        return "sleeping"
    if 7 <= hour < 9:
        return "morning_rush"
    if 9 <= hour < 14:
        return "set_busy"
    if 14 <= hour < 17:
        return "afternoon_gap"
    if 17 <= hour < 21:
        return "after_work"
    return "night_alone"


def describe_routine_slot(routine_slot: str) -> str:
    """返回时间槽位的中文标签。"""
    return _ROUTINES.get(routine_slot, _ROUTINES["night_alone"])["label"]


def build_observation_seed(
    user_id: str,
    now_local: datetime,
    routine_slot: str,
    *,
    bucket_minutes: int = 5,
) -> int:
    """按用户与时间桶生成稳定 seed，避免同一时间段抖动。"""
    bucket = (now_local.hour * 60 + now_local.minute) // max(1, bucket_minutes)
    raw = f"{user_id}|{now_local:%Y-%m-%d}|{bucket}|{routine_slot}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def build_observation_context(
    user_id: str,
    now_local: datetime,
    *,
    weather_summary: str = "",
    mood: str = "平静",
) -> Dict[str, str]:
    """根据时间槽位与稳定随机生成观察基础上下文。"""
    routine_slot = resolve_routine_slot(now_local)
    routine = _ROUTINES.get(routine_slot, _ROUTINES["night_alone"])
    rng = random.Random(build_observation_seed(user_id, now_local, routine_slot))
    scene_detail = rng.choice(routine["scene_details"])

    accident_code = ""
    accident_text = ""
    if any(token in (weather_summary or "") for token in ("雨", "雪", "雷")) and rng.random() < 0.45:
        accident_code, accident_text = rng.choice(_RAIN_ACCIDENTS)
    elif mood in _MOOD_ACCIDENTS and rng.random() < 0.4:
        accident_code, accident_text = _MOOD_ACCIDENTS[mood]
    elif rng.random() < 0.2:
        accident_code, accident_text = rng.choice(_DAILY_ACCIDENTS)

    return {
        "routine_slot": routine_slot,
        "routine_label": routine["label"],
        "scene_detail": scene_detail,
        "accident_code": accident_code,
        "accident_text": accident_text,
    }
