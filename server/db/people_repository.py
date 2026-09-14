# -*- coding: utf-8 -*-
"""用户域访问层：comic_people / comic_invitation_code / comic_login_errorlog / comic_points。

独立 comic 库，表名 comic_ 前缀。SQL 写方言无关形式（%s 占位、NOW()、FOR UPDATE），
由 server.db.connection 的 SQLite/MySQL 工厂负责落地。

内测期决策（写死在语义里，可调通过 comic_app_config）：
- 注册必须填邀请码（核销 comic_invitation_code.invalid=1→0）
- 注册成功发 2 个邀请码给新用户
- 注册送积分、邀请人返积分按 comic_app_config 单行的值
"""

import hashlib
import secrets
import time
from typing import Any, Optional, Tuple

from server.db.connection import get_db

CHAR_SET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
INVITATION_CODE_LENGTH = 6

# 登录失败锁定：5 次/300s → 锁 60 分钟
LOGIN_ERROR_WINDOW_SECONDS = 300
LOGIN_ERROR_THRESHOLD = 5
LOGIN_LOCK_MINUTES = 60


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_invitation_code() -> str:
    return "".join(secrets.choice(CHAR_SET) for _ in range(INVITATION_CODE_LENGTH))


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def find_by_phone(phone: str) -> Optional[dict[str, Any]]:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM comic_people WHERE people_phone = %s", (phone,))
        return cur.fetchone()


def find_frozen_by_phone(phone: str) -> Optional[dict[str, Any]]:
    """冻结拦截：frozen_datetime >= NOW() 视为冻结中。"""
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT people_id, people_reason, frozen_datetime FROM comic_people "
            "WHERE frozen_datetime >= NOW() AND people_phone = %s",
            (phone,),
        )
        return cur.fetchone()


def find_by_id(people_id) -> Optional[dict[str, Any]]:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM comic_people WHERE people_id = %s", (people_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# 登录失败锁定
# ---------------------------------------------------------------------------

def is_login_locked(username: str) -> bool:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(1) AS cnt FROM comic_login_errorlog "
            "WHERE `user` = %s AND disable = 'Y' "
            "AND login_time > FROM_UNIXTIME(%s)",
            (username, int(time.time()) - LOGIN_LOCK_MINUTES * 60),
        )
        row = cur.fetchone() or {}
        return int(row.get("cnt") or 0) >= 1


def record_login_error(username: str, ip: str) -> bool:
    """写一条失败记录；300s 内累计 >=5 条则追加 disable='Y' 锁定记录。返回是否锁定。"""
    now = int(time.time())
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO comic_login_errorlog (`user`, login_time, ip, disable) "
                "VALUES (%s, NOW(), %s, 'N')",
                (username, ip),
            )
            cur.execute(
                "SELECT COUNT(1) AS cnt FROM comic_login_errorlog "
                "WHERE `user` = %s AND login_time > FROM_UNIXTIME(%s)",
                (username, now - LOGIN_ERROR_WINDOW_SECONDS),
            )
            cnt = int((cur.fetchone() or {}).get("cnt") or 0)
            locked = False
            if cnt >= LOGIN_ERROR_THRESHOLD:
                cur.execute(
                    "INSERT INTO comic_login_errorlog (`user`, login_time, disable) "
                    "VALUES (%s, NOW(), 'Y')",
                    (username,),
                )
                locked = True
            conn.commit()
            return locked
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# 注册（单事务）
# ---------------------------------------------------------------------------

def register_user(
    *, name: str, phone: str, password_sha: str, invitation_code: str, ip: str
) -> Tuple[bool, str]:
    """注册新用户，单事务完成全部副作用。返回 (ok, 中文错误文案)。"""
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        try:
            # 1) 校验邀请码（先查后占，行锁防并发核销同一码）
            cur.execute(
                "SELECT id FROM comic_invitation_code "
                "WHERE invitation_code = %s AND invalid = 1 FOR UPDATE",
                (invitation_code,),
            )
            code_row = cur.fetchone()
            if not code_row:
                conn.rollback()
                return False, "邀请码错误或失效！"

            # 2) 手机号唯一
            cur.execute(
                "SELECT people_id FROM comic_people WHERE people_phone = %s", (phone,)
            )
            if cur.fetchone():
                conn.rollback()
                return False, "用户已存在"

            # 3) 建用户
            cur.execute(
                "INSERT INTO comic_people (people_name, people_phone, people_password, "
                "people_status, people_ip, people_datetime, invitation_code) "
                "VALUES (%s, %s, %s, 'PASS', %s, NOW(), %s)",
                (name, phone, password_sha, ip, invitation_code),
            )
            people_id = cur.lastrowid

            # 4) 新用户发 2 个邀请码
            for _ in range(2):
                cur.execute(
                    "INSERT INTO comic_invitation_code (people_id, invitation_code, invalid) "
                    "VALUES (%s, %s, 1)",
                    (people_id, generate_invitation_code()),
                )

            # 5) 读配置：注册送积分 + 邀请返积分
            cur.execute(
                "SELECT register_points, recommend_points FROM comic_app_config LIMIT 1"
            )
            app_row = cur.fetchone() or {}
            register_pts = float(app_row.get("register_points") or 0)
            recommend_pts = float(app_row.get("recommend_points") or 0)

            if register_pts > 0:
                cur.execute(
                    "UPDATE comic_people SET points = %s WHERE people_id = %s",
                    (register_pts, people_id),
                )
                cur.execute(
                    "INSERT INTO comic_points (people_id, old_num, update_num, points_num, "
                    "receipts, consumption, remarks, delete_flag, create_time, update_time) "
                    "VALUES (%s, 0, %s, %s, '+', '注册送积分', NULL, 0, NOW(), NOW())",
                    (people_id, register_pts, register_pts),
                )

            # 6) 邀请人返积分：按 people_id 持有该码的人（comic_invitation_code.people_id）
            if recommend_pts > 0:
                cur.execute(
                    "SELECT people_id FROM comic_invitation_code "
                    "WHERE invitation_code = %s AND people_id > 0",
                    (invitation_code,),
                )
                inviter_row = cur.fetchone()
                if inviter_row:
                    inviter_id = inviter_row["people_id"]
                    cur.execute(
                        "SELECT points FROM comic_people WHERE people_id = %s FOR UPDATE",
                        (inviter_id,),
                    )
                    inviter = cur.fetchone() or {}
                    old_bal = float(inviter.get("points") or 0)
                    new_bal = old_bal + recommend_pts
                    cur.execute(
                        "INSERT INTO comic_points (people_id, old_num, update_num, "
                        "points_num, receipts, consumption, remarks, delete_flag, "
                        "create_time, update_time) "
                        "VALUES (%s, %s, %s, %s, '+', '邀请送积分', NULL, 0, NOW(), NOW())",
                        (inviter_id, old_bal, recommend_pts, new_bal),
                    )
                    cur.execute(
                        "UPDATE comic_people SET points = %s WHERE people_id = %s",
                        (new_bal, inviter_id),
                    )

            # 7) 核销邀请码
            cur.execute(
                "UPDATE comic_invitation_code SET invalid = 0 WHERE id = %s",
                (code_row["id"],),
            )
            conn.commit()
            return True, ""
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# 用户详情 / 邀请码 / 积分
# ---------------------------------------------------------------------------

def get_people_detail(people_id) -> Optional[dict[str, Any]]:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT people_id AS peopleId, people_name AS peopleName, "
            "people_phone AS peoplePhone, people_datetime AS peopleDatetime, "
            "points, people_status AS peopleState "
            "FROM comic_people WHERE people_id = %s",
            (people_id,),
        )
        return cur.fetchone()


def list_invitation_codes(people_id) -> list[dict[str, Any]]:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, invitation_code AS invitationCode, "
            "create_time AS createTime, invalid "
            "FROM comic_invitation_code WHERE people_id = %s "
            "ORDER BY id DESC",
            (people_id,),
        )
        return cur.fetchall() or []


def get_points_balance(people_id) -> float:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT points FROM comic_people WHERE people_id = %s", (people_id,)
        )
        row = cur.fetchone() or {}
        return float(row.get("points") or 0.0)


def list_points_history(people_id, page_number: int, page_size: int) -> dict[str, Any]:
    page_number = max(int(page_number or 1), 1)
    page_size = min(max(int(page_size or 10), 1), 100)
    offset = (page_number - 1) * page_size
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(1) AS cnt FROM comic_points "
            "WHERE people_id = %s AND delete_flag = 0",
            (people_id,),
        )
        total_row = int((cur.fetchone() or {}).get("cnt") or 0)
        total_page = max((total_row + page_size - 1) // page_size, 1)
        cur.execute(
            "SELECT consumption, update_num, points_num, receipts, remarks, "
            "create_time FROM comic_points "
            "WHERE people_id = %s AND delete_flag = 0 "
            "ORDER BY id DESC LIMIT %s OFFSET %s",
            (people_id, page_size, offset),
        )
        rows = cur.fetchall() or []

    items = []
    for row in rows:
        change = float(row.get("update_num") or 0)
        if row.get("receipts") == "-":
            change = -change
        create_time = row.get("create_time")
        items.append(
            {
                "purpose": row.get("consumption") or "",
                "use_time": (
                    create_time.isoformat(sep=" ")
                    if hasattr(create_time, "isoformat")
                    else (str(create_time)[:19] if create_time else None)
                ),
                "change": change,
                "use_points": float(row.get("update_num") or 0),
                "balance": float(row.get("points_num") or 0),
                "remarks": row.get("remarks") or "",
            }
        )
    return {
        "list": items,
        "currPage": page_number,
        "totalPage": total_page,
        "totalRow": total_row,
    }


def insert_anonymous_invitation(code: str) -> None:
    """匿名发码（landing 自助/管理员批量发）。people_id=0、invalid=1。"""
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO comic_invitation_code (people_id, invitation_code, invalid) "
                "VALUES (0, %s, 1)",
                (code,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# 项目归属（comic_project：projects/ 目录是纯文件，靠这张表按人过滤）
# ---------------------------------------------------------------------------

def create_project_ownership(project_id: str, people_id, title: str = None) -> None:
    """新项目落归属。projects/{pid}/ 目录由 store.init_dirs 建好，这里只记索引。"""
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO comic_project (project_id, people_id, title) "
                "VALUES (%s, %s, %s)",
                (project_id, int(people_id), title),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def project_owner(project_id: str) -> Optional[int]:
    """查项目 owner；项目不存在返回 None。"""
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT people_id FROM comic_project WHERE project_id = %s", (project_id,)
        )
        row = cur.fetchone()
        return int(row["people_id"]) if row else None


def list_project_ids_by_owner(people_id) -> list[str]:
    """当前用户的项目 id 列表（供 list_projects 过滤）。"""
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT project_id FROM comic_project WHERE people_id = %s "
            "ORDER BY create_time DESC",
            (int(people_id),),
        )
        return [r["project_id"] for r in (cur.fetchall() or [])]
