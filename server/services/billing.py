# -*- coding: utf-8 -*-
"""积分计费：生成成本累计 + 单事务扣费 + 流水。

模型（内测期 1:1，比例可调于 comic_app_config）：
- 故事模型：按 token 计费   成本 = total_tokens / 1000 * story_cost_per_1k_token
- 生图：    按张数计费     成本 = 图片张数 * image_cost_per_unit

设计：
- llm.py / image_gen.py 是底层调用点，它们把「这次调用的 token/张数」记进
  一个**线程本地的计量器**（`usage_meter`）。生成任务在后台线程跑，计量器
  随任务线程生命周期累计。
- 任务收尾时调用 ``settle_task_usage(people_id)`` 把累计成本一次性扣费 +
  写 comic_points 流水（单事务）。
- 内测策略：余额不足不阻断生成（先记账），只把余额扣到 0 并记负向流水备注。
  要真扣费拦截时用 ``check_balance`` 在 generate 入口预检。

因为扣费发生在生成**成功之后**，天然幂等——没扣成功的钱不进流水。
"""

import threading
from typing import Optional

from server.db.connection import get_db

# 线程本地计量器：一个生成任务线程累计 {tokens, images}
_meter = threading.local()


def _state() -> dict:
    if not hasattr(_meter, "v"):
        _meter.v = {"tokens": 0, "images": 0}
    return _meter.v


def reset_meter() -> None:
    """任务线程开始时清零。"""
    _meter.v = {"tokens": 0, "images": 0}


def record_llm_usage(usage) -> None:
    """llm._request 调用后回传 usage（OpenAI usage 对象或 dict）。"""
    if usage is None:
        return
    tokens = getattr(usage, "total_tokens", None)
    if tokens is None and isinstance(usage, dict):
        tokens = usage.get("total_tokens")
    if tokens:
        _state()["tokens"] += int(tokens)


def record_image(count: int = 1) -> None:
    """每生成一张图计一次（generate/edit 各一次）。"""
    _state()["images"] += count


def current_usage() -> dict:
    return dict(_state())


# ---------------------------------------------------------------------------
# 成本与结算
# ---------------------------------------------------------------------------

def _get_rates() -> tuple[float, float]:
    """读 comic_app_config 的两个比例；读不到用默认 1.0。"""
    try:
        with get_db().get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT story_cost_per_1k_token, image_cost_per_unit "
                "FROM comic_app_config LIMIT 1"
            )
            row = cur.fetchone() or {}
            return (
                float(row.get("story_cost_per_1k_token") or 1.0),
                float(row.get("image_cost_per_unit") or 1.0),
            )
    except Exception:
        return 1.0, 1.0


def compute_cost(usage: dict) -> float:
    """usage={tokens, images} → 积分成本。"""
    story_rate, image_rate = _get_rates()
    tokens = int(usage.get("tokens") or 0)
    images = int(usage.get("images") or 0)
    cost = (tokens / 1000.0) * story_rate + images * image_rate
    return round(cost, 2)


def get_balance(people_id) -> float:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT points FROM comic_people WHERE people_id = %s", (int(people_id),)
        )
        row = cur.fetchone() or {}
        return float(row.get("points") or 0.0)


def check_balance(people_id, min_points: float = 1.0) -> bool:
    """生成前预检：余额是否 >= min_points。内测期可用于拦 0 余额用户。"""
    return get_balance(people_id) >= min_points


def settle_task_usage(
    people_id, usage: dict, *, project_id: str = "", action: str = ""
) -> Optional[float]:
    """任务收尾：把 usage 换算成积分，单事务扣减 + 写流水。

    返回实际扣减额；usage 为空或成本为 0 返回 None（不写流水）。
    余额不足时扣到 0 为止（不扣负），流水备注里记实际成本。
    """
    cost = compute_cost(usage)
    if cost <= 0:
        return None

    people_id = int(people_id)
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT points FROM comic_people WHERE people_id = %s FOR UPDATE",
                (people_id,),
            )
            row = cur.fetchone() or {}
            old_bal = float(row.get("points") or 0.0)
            # 内测宽松：只扣到 0，不扣负（成本记流水备注供对账）
            deducted = min(cost, max(old_bal, 0.0))
            new_bal = round(old_bal - deducted, 2)
            remarks = (
                f"项目{project_id} {action}".strip()
                + f"；token={usage.get('tokens',0)} 图={usage.get('images',0)}"
                + (f"；成本{cost}余额不足仅扣{deducted}" if deducted < cost else "")
            )
            cur.execute(
                "UPDATE comic_people SET points = %s WHERE people_id = %s",
                (new_bal, people_id),
            )
            cur.execute(
                "INSERT INTO comic_points (people_id, old_num, update_num, points_num, "
                "receipts, consumption, remarks, delete_flag, create_time, update_time) "
                "VALUES (%s, %s, %s, %s, '-', '漫画生成', %s, 0, NOW(), NOW())",
                (people_id, old_bal, deducted, new_bal, remarks[:250]),
            )
            conn.commit()
            return deducted
        except Exception:
            conn.rollback()
            raise
