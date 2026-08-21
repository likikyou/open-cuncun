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
            "被子歪到一边，床头还放着没来得及收好的耳机和水杯",
            "抱着枕头缩成一团，床头灯早就熄灭了",
            "枕边的手机被随手扣着，充电线歪歪扭扭搭在床沿边",
        ),
    },
    "morning_rush": {
        "label": "清晨准备与通勤",
        "scene_details": (
            "一边吃着吐司一边整理背包，外套拉链都还没完全拉好",
            "地铁口的风迎面吹来，背着包在人群里走得飞快",
            "桌边的纸杯咖啡还冒着热气，今天的待办已经摊开在眼前",
        ),
    },
    "set_busy": {
        "label": "白天专注工作",
        "scene_details": (
            "工作区的灯光有些发闷，屏幕上的任务进度还在不断更新",
            "资料和常用工具摊在桌边，忙得连坐都顾不上坐稳",
            "刚处理完一项紧急任务，手边的新提醒又亮了起来，动作几乎没停",
        ),
    },
    "afternoon_gap": {
        "label": "下午短暂休息",
        "scene_details": (
            "窗边的光线有点灰，缩在座椅里捧着杯子发呆",
            "桌边的冰美式杯壁还凝着水，撑着下巴给自己留出一小段喘气时间",
            "靠着椅背揉了揉发酸的肩颈，终于暂时放下手里的事情",
        ),
    },
    "after_work": {
        "label": "结束工作与晚高峰",
        "scene_details": (
            "便利店的冷白灯落在肩上，拎着便当盒站在货架前犹豫了一会儿",
            "晚高峰的人流不断向前，背着包走在人群里，神情已经有点放空",
            "刚结束一天的工作，外套松松搭在手臂上，步子比白天慢了不少",
        ),
    },
    "night_alone": {
        "label": "夜间独处",
        "scene_details": (
            "沙发上摊着一条毯子，盘腿窝着看书，手边还摆着没喝完的水杯",
            "刚洗完澡的潮气还没散，坐在床边慢吞吞擦着头发",
            "客厅只开了一盏小灯，下巴抵在膝盖上，指尖无意识划着手机屏幕",
        ),
    },
}

_RAIN_ACCIDENTS = (
    ("rain_delay", "鞋边被雨点溅得发暗，只好先缩在屋檐边等这一阵过去"),
    ("rain_hideout", "临时躲进便利店门口，拎着背包等雨势变小"),
    ("rain_messy", "肩头沾了一点潮气，头发尾梢也被风吹得有点乱"),
)

_MOOD_ACCIDENTS = {
    "愤怒": ("mood_irritated", "把吸管咬得有点扁，动作里都带着一点不痛快"),
    "生气": ("mood_irritated", "把吸管咬得有点扁，动作里都带着一点不痛快"),
    "焦虑": ("mood_restless", "指尖老是在杯壁边蹭来蹭去，像是怎么放都不太对劲"),
    "难过": ("mood_low", "低着头把袖口扯平了一次又一次，整个人显得有点蔫"),
    "思念": ("mood_soft", "盯着手机亮起又暗下的那一瞬，眼神跟着轻轻晃了一下"),
    "撒娇": ("mood_playful", "把杯子转了半圈，唇角压着一点像是故意不肯承认的笑"),
}

_DAILY_ACCIDENTS = (
    ("powder_spill", "刚才那支笔掉了一次，弯腰捡起来时还轻轻啧了一声"),
    ("mascara_roll", "水杯盖滚到了桌角边，抬手去够的时候动作明显顿了一下"),
    ("takeout_wrong", "外卖送来的口味不太对，看了两眼后还是先放到了一边"),
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
