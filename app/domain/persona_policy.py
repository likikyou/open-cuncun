"""角色边界策略的纯数据模型与进程内活动配置。"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class PersonaBoundaryPolicy:
    """供多个领域规则共享的角色边界标记。"""

    assistant_private_claim_markers: tuple[str, ...] = ()
    persona_private_subject_markers: tuple[str, ...] = ()
    persona_private_life_markers: tuple[str, ...] = ()
    user_self_life_markers: tuple[str, ...] = ()
    memory_audit_markers: tuple[str, ...] = ()
    assistant_self_markers: tuple[str, ...] = ()


PERSONA_POLICY_MARKER_FIELDS = tuple(field.name for field in fields(PersonaBoundaryPolicy))


PUBLIC_PERSONA_BOUNDARY_POLICY = PersonaBoundaryPolicy(
    assistant_private_claim_markers=(
        "客户",
        "行程",
        "航班",
        "机票",
        "登机牌",
        "出差",
        "工作",
        "上班",
        "下班",
        "开会",
        "加班",
        "办公室",
        "酒店",
        "机场",
        "车站",
        "咖啡店",
        "餐厅",
        "楼下",
        "家里",
    ),
    persona_private_subject_markers=("你", "你们"),
    persona_private_life_markers=(
        "休息",
        "上班",
        "下班",
        "工作",
        "忙吗",
        "在忙",
        "在干嘛",
        "干嘛呢",
        "行程",
        "安排",
        "客户",
        "航班",
        "机票",
        "登机",
        "出差",
        "去哪里",
        "去哪",
        "在哪里",
        "在哪",
        "吃饭了吗",
        "睡了吗",
        "办公室",
        "酒店",
        "机场",
        "车站",
        "咖啡店",
        "餐厅",
        "楼下",
        "家里",
    ),
    user_self_life_markers=(
        "我的工作",
        "我工作",
        "我上班",
        "我休息",
        "我今天工作",
        "我明天工作",
        "我最近工作",
        "我今天休息",
        "我明天休息",
        "我开会",
        "我要开会",
        "我今天开会",
        "我今天要开会",
        "我明天开会",
        "我明天要开会",
        "我加班",
        "我今天加班",
        "我明天加班",
        "我今晚加班",
        "我的行程",
        "我的安排",
        "我的客户",
        "我的航班",
        "我的机票",
        "我出差",
        "我去",
        "我要去",
        "我今天去",
        "我明天去",
        "我刚到",
        "我在",
        "我住在",
        "我家里",
        "用户去",
        "用户要去",
        "用户今天去",
        "用户明天去",
        "用户刚到",
        "用户出差",
        "用户开会",
        "用户要开会",
        "用户今天开会",
        "用户今天要开会",
        "用户明天开会",
        "用户明天要开会",
        "用户加班",
        "用户今天加班",
        "用户明天加班",
        "用户今晚加班",
        "用户在",
        "用户住在",
        "用户家里",
        "用户的工作",
        "用户的行程",
        "用户的客户",
        "用户的航班",
        "用户的机票",
    ),
    memory_audit_markers=(
        "客户",
        "行程",
        "航班",
        "机票",
        "登机牌",
        "出差",
        "工作",
        "上班",
        "下班",
        "开会",
        "加班",
        "办公室",
        "酒店",
        "机场",
        "车站",
        "咖啡店",
        "餐厅",
        "楼下",
        "家里",
    ),
    assistant_self_markers=("助手", "角色"),
)


def _merge_markers(current: Iterable[str], extension: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for marker in (*tuple(current), *tuple(extension)):
        normalized = marker.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
    return tuple(merged)


def extend_persona_boundary_policy(
    base_policy: PersonaBoundaryPolicy,
    extensions: Mapping[str, Iterable[str]],
) -> PersonaBoundaryPolicy:
    """在公共默认策略上追加部署侧标记，并保持顺序与去重。"""
    unknown_fields = set(extensions) - set(PERSONA_POLICY_MARKER_FIELDS)
    if unknown_fields:
        raise ValueError("persona policy contains unsupported marker fields")

    values = {}
    for field_name in PERSONA_POLICY_MARKER_FIELDS:
        extension = extensions.get(field_name, ())
        if isinstance(extension, (str, bytes)):
            raise TypeError("persona policy marker extension must be an iterable of strings")
        values[field_name] = _merge_markers(getattr(base_policy, field_name), extension)
    return PersonaBoundaryPolicy(**values)


_active_persona_boundary_policy = PUBLIC_PERSONA_BOUNDARY_POLICY


def configure_persona_boundary_policy(policy: PersonaBoundaryPolicy) -> None:
    """配置当前进程使用的领域策略；应在启动阶段调用。"""
    if not isinstance(policy, PersonaBoundaryPolicy):
        raise TypeError("policy must be a PersonaBoundaryPolicy")
    global _active_persona_boundary_policy
    _active_persona_boundary_policy = policy


def get_persona_boundary_policy() -> PersonaBoundaryPolicy:
    """返回当前进程活动的角色边界策略。"""
    return _active_persona_boundary_policy
