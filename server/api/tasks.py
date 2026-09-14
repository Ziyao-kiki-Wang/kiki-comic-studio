# -*- coding: utf-8 -*-
"""后台任务表：内存字典 + 状态持久化（projects/_tasks.json）。

- 任务在 daemon 线程里跑，全局一把执行锁串行（避免并发画图互相踩、
  也避免 stdout 日志捕获交叉污染）。
- 状态变化即落盘；进程重启时 load_tasks() 把上次的 pending/running
  标成 failed（孤儿任务恢复）。
"""

import contextlib
import json
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable

from server.config import PROJECTS_DIR

TASKS_FILE = PROJECTS_DIR / "_tasks.json"

_tasks: dict[str, "Task"] = {}
_guard = threading.Lock()
_exec_lock = threading.Lock()


@dataclass
class Task:
    task_id: str
    kind: str  # create_project / generate
    project_id: str
    detail: dict = field(default_factory=dict)  # 请求参数（action、scene_id 等）
    status: str = "pending"  # pending / running / done / failed
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    people_id: int | None = None  # 计费归属（生成任务带，用于收尾扣费）
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


def _save_locked():
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(
        json.dumps(
            [t.to_dict() for t in _tasks.values()], ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )


def load_tasks():
    """启动时恢复任务表；上次的 pending/running 都是孤儿，标 failed。"""
    if not TASKS_FILE.exists():
        return
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    with _guard:
        for item in data:
            try:
                t = Task(**item)
            except TypeError:
                continue
            if t.status in ("pending", "running"):
                t.status = "failed"
                t.error = "服务重启，任务中断（孤儿任务恢复）"
            _tasks[t.task_id] = t
        _save_locked()


def get_task(task_id: str) -> Task | None:
    with _guard:
        return _tasks.get(task_id)


def active_for_project(project_id: str):
    with _guard:
        return next(
            (
                t
                for t in _tasks.values()
                if t.project_id == project_id and t.status in ("pending", "running")
            ),
            None,
        )


def _set(t: Task, status: str, error: str | None = None):
    with _guard:
        t.status = status
        t.error = error
        t.updated_at = time.time()
        _save_locked()


class _LogWriter:
    """把 print 输出按行收进任务日志（配合 redirect_stdout 用）。"""

    def __init__(self, task: Task):
        self.task = task
        self.buf = ""

    def write(self, s: str):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                with _guard:
                    self.task.logs.append(line)
                    self.task.updated_at = time.time()

    def flush(self):
        if self.buf.strip():
            with _guard:
                self.task.logs.append(self.buf.strip())
                self.task.updated_at = time.time()
            self.buf = ""


def submit(
    kind: str,
    project_id: str,
    detail: dict,
    fn: Callable[[], None],
    people_id: int | None = None,
) -> Task:
    t = Task(
        task_id=uuid.uuid4().hex[:12],
        kind=kind,
        project_id=project_id,
        detail=detail,
        people_id=int(people_id) if people_id is not None else None,
    )
    with _guard:
        _tasks[t.task_id] = t
        _save_locked()
    threading.Thread(target=_run, args=(t, fn), daemon=True).start()
    return t


def _settle(t: Task):
    """任务结束：若带 people_id 且计费面有消耗，单事务扣积分 + 写流水。

    只在生成类任务里才计费（kind in 生成/素材）。读库失败静默——
    计费故障不能反过来打断已完成的生成。
    """
    if t.people_id is None:
        return
    try:
        from server.services import billing
        usage = billing.current_usage()
        deducted = billing.settle_task_usage(
            t.people_id, usage,
            project_id=t.project_id,
            action=t.detail.get("action", t.kind),
        )
        if deducted:
            print(f"[计费] 本次消耗 {deducted} 积分（token={usage['tokens']} 图={usage['images']}）")
    except Exception as e:
        print(f"[计费] 结算失败（不阻断任务）：{e}")


def _run(t: Task, fn: Callable[[], None]):
    from server.services import billing
    billing.reset_meter()  # 任务线程的计量器清零
    with _exec_lock:
        _set(t, "running")
        try:
            with (
                contextlib.redirect_stdout(_LogWriter(t)),
                contextlib.redirect_stderr(_LogWriter(t)),
            ):
                result = fn()
                if isinstance(result, dict):
                    with _guard:
                        t.result = result
        except Exception:
            tb = traceback.format_exc(limit=8)
            with _guard:
                t.logs.append(tb)
            last = tb.strip().splitlines()[-1] if tb.strip() else "unknown error"
            _set(t, "failed", error=last)
        else:
            _set(t, "done")
        finally:
            _settle(t)  # 不管成败都结算已发生的消耗（失败的也消耗了 API）
