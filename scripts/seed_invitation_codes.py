# -*- coding: utf-8 -*-
"""邀请码发码脚本：内测冷启动用。

注册必须填邀请码，但新库没有任何可用码——这个脚本生成一批匿名码
（people_id=0），供内测分发。

用法：
    python -m scripts.seed_invitation_codes           # 默认发 10 个
    python -m scripts.seed_invitation_codes 50        # 发 50 个
    python -m scripts.seed_invitation_codes 0         # 只列出现有可用码
"""

import sys
from pathlib import Path

# 让 `python -m scripts.xxx` 能 import server.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.db import people_repository
from server.db.connection import get_db


def list_valid_codes() -> list[str]:
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT invitation_code FROM comic_invitation_code "
            "WHERE invalid = 1 ORDER BY id DESC LIMIT 200"
        )
        return [r["invitation_code"] for r in (cur.fetchall() or [])]


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    for _ in range(max(count, 0)):
        code = people_repository.generate_invitation_code()
        people_repository.insert_anonymous_invitation(code)
    codes = list_valid_codes()
    print(f"已生成 {max(count, 0)} 个；当前可用邀请码 {len(codes)} 个：")
    for c in codes:
        print(f"  {c}")


if __name__ == "__main__":
    main()
