"""批量刷新余额的异步任务管理 (CEO 2026-05-17)。

财务系统"全部刷新余额"按一次会跑 5+ 分钟(7 个账号 × 30-60 秒/个)。
HTTP 长连接会被 Nginx/前端超时切断,所以改成"创建任务 → 后台跑 → 前端轮询进度"。

任务状态保存在进程内存里, 后端重启会丢失 (CEO 接受 — 重启时正在跑的批量
最多重来一次, 不影响数据正确性)。
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AccountRefreshResult:
    """单个账号刷新结果。"""

    account_id: int
    account_name: str
    success: bool
    balance: Optional[str] = None
    currency: Optional[str] = None
    message: Optional[str] = None


@dataclass
class RefreshJob:
    """整批刷新任务状态。"""

    job_id: str
    total: int
    completed: int = 0
    succeeded: int = 0
    failed: int = 0
    current_account_id: Optional[int] = None
    current_account_name: Optional[str] = None
    results: list[AccountRefreshResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None


# 全局状态 (进程内). 重启后丢失.
_jobs: dict[str, RefreshJob] = {}
_lock = threading.Lock()


def create_job(total: int) -> RefreshJob:
    """新建一个任务, 返回任务句柄。"""
    job_id = uuid.uuid4().hex[:12]
    job = RefreshJob(job_id=job_id, total=total)
    with _lock:
        _jobs[job_id] = job
        # 自动清理超过 100 个的旧任务 (保留最近 100 条)
        if len(_jobs) > 100:
            sorted_jobs = sorted(
                _jobs.values(), key=lambda j: j.started_at, reverse=True
            )
            keep = {j.job_id for j in sorted_jobs[:100]}
            for jid in list(_jobs):
                if jid not in keep:
                    del _jobs[jid]
    return job


def get_job(job_id: str) -> Optional[RefreshJob]:
    """查任务状态, 不存在返回 None。"""
    with _lock:
        return _jobs.get(job_id)


def update_progress(
    job_id: str,
    *,
    current_account_id: Optional[int] = None,
    current_account_name: Optional[str] = None,
) -> None:
    """更新"正在刷哪个账号"。"""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.current_account_id = current_account_id
        job.current_account_name = current_account_name


def append_result(job_id: str, result: AccountRefreshResult) -> None:
    """添加一个账号的刷新结果, 累计计数。"""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.results.append(result)
        job.completed += 1
        if result.success:
            job.succeeded += 1
        else:
            job.failed += 1


def finish_job(job_id: str) -> None:
    """标记任务完成。"""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.finished_at = datetime.now()
        job.current_account_id = None
        job.current_account_name = None
