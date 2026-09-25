"""拍摄通告业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "notice"
SHOOTING_MODULE = "shooting"
REQUIRED_FIELDS = ["通告编号", "拍摄日期", "集合时间"]
STATUS_ORDER = ["待下发", "已下发", "执行中", "已完成"]
ACTION_RULES = {"下发通告": "已下发", "开始执行": "执行中", "确认完成": "已完成"}
NEGATIVE_ACTIONS = []

# 批量下发时逐条校验的字段：集合时间、拍摄地点、出勤人员，问题按字段分别说明
BATCH_EDITABLE_FIELDS = ["集合时间", "拍摄地点", "出勤人员", "用车安排"]
CALL_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# 批次记录独立存放，不并入通告表：批量结果只追加新通告单，不覆盖既有数据
_BATCHES: list[dict[str, Any]] = []


def _validate_dispatch(values: dict[str, str]) -> list[str]:
    """集合时间、拍摄地点、出勤人员分别校验，问题逐条列出。"""
    problems: list[str] = []
    if not values["拍摄日编号"]:
        problems.append("缺少拍摄日编号")
    if not values["集合时间"]:
        problems.append("缺少集合时间")
    elif not CALL_TIME_PATTERN.match(values["集合时间"]):
        problems.append("集合时间格式需为 HH:MM（24 小时制）")
    if not values["拍摄地点"]:
        problems.append("缺少拍摄地点")
    if not values["出勤人员"]:
        problems.append("缺少出勤人员")
    return problems


def _find_shooting_day(day_no: str) -> dict[str, Any] | None:
    for row in store.rows(SHOOTING_MODULE):
        if str(row.get("拍摄日编号", "")) == day_no:
            return row
    return None


def _day_already_dispatched(day_no: str) -> bool:
    """同一拍摄日只允许批量生成一张通告单，重复提交不会重复创建。"""
    return any(
        str(row.get("拍摄日编号", "")) == day_no and row.get("批次号")
        for row in store.rows(MODULE)
    )


def _next_notice_no(rows: list[dict[str, Any]]) -> str:
    """在现有通告编号基础上顺延，保证批量生成的编号不与单条登记冲突。"""
    max_no = 0
    for row in rows:
        prefix, _, suffix = str(row.get("通告编号", "")).partition("NOTI-")
        if prefix == "" and suffix.isdigit():
            max_no = max(max_no, int(suffix))
    return f"NOTI-{max_no + 1:04d}"


def _find_batch(*, batch_no: str | None = None, batch_key: str | None = None) -> dict[str, Any] | None:
    for batch in _BATCHES:
        if batch_no and batch["批次号"] == batch_no:
            return batch
        if batch_key and batch["batch_key"] == batch_key:
            return batch
    return None


def _refresh_batch_counts(batch: dict[str, Any]) -> None:
    batch["total"] = len(batch["items"])
    batch["succeeded"] = sum(1 for item in batch["items"] if item["ok"])
    batch["failed"] = batch["total"] - batch["succeeded"]


def _batch_message(batch: dict[str, Any]) -> str:
    if batch["failed"] == 0:
        return f"批量下发完成：{batch['succeeded']} 条通告单全部生成并下发"
    return f"批量下发完成：成功 {batch['succeeded']} 条，失败 {batch['failed']} 条，可修正后只重试失败项"


class NoticeService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        batch: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通告编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if batch:
            rows = [row for row in rows if str(row.get("批次号", "")) == batch]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"拍摄通告单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于拍摄通告可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"拍摄通告单已{action}"

    # ---- 批量下发 ----

    def list_batches(self) -> list[dict[str, Any]]:
        """批次摘要列表，最新的批次排在前面。"""
        return [
            {
                "批次号": batch["批次号"],
                "total": batch["total"],
                "succeeded": batch["succeeded"],
                "failed": batch["failed"],
            }
            for batch in reversed(_BATCHES)
        ]

    def get_batch(self, batch_no: str) -> dict[str, Any] | None:
        return _find_batch(batch_no=batch_no)

    def dispatch_batch(
        self,
        batch_key: str | None,
        items: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """一次提交多个拍摄日，逐条生成并下发通告单。

        返回 (批次记录, 提示信息, 是否全部成功)。携带相同 batch_key 重复提交时
        直接返回首次结果，不会重复创建通告单。
        """
        if not items:
            return None, "未选择任何拍摄日，无法批量下发", False
        if batch_key:
            existing = _find_batch(batch_key=batch_key)
            if existing is not None:
                return existing, f"批次 {existing['批次号']} 已提交过，本次未重复创建", existing["failed"] == 0
        batch: dict[str, Any] = {
            "id": len(_BATCHES) + 1,
            "批次号": f"NOTIB-{len(_BATCHES) + 1:04d}",
            "batch_key": batch_key or "",
            "items": [],
            "total": 0,
            "succeeded": 0,
            "failed": 0,
        }
        for item in items:
            batch["items"].append(self._dispatch_one(item, batch["批次号"]))
        _refresh_batch_counts(batch)
        _BATCHES.append(batch)
        return batch, _batch_message(batch), batch["failed"] == 0

    def retry_batch(
        self,
        batch_no: str,
        corrections: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """只重试批次内失败的通告；成功项保持原样，不会被重复创建。"""
        batch = _find_batch(batch_no=batch_no)
        if batch is None:
            return None, f"下发批次 {batch_no} 不存在", False
        fixes = {
            str(item.get("拍摄日编号") or "").strip(): item
            for item in corrections
            if str(item.get("拍摄日编号") or "").strip()
        }
        retried = 0
        for item in batch["items"]:
            if item["ok"]:
                continue
            fix = fixes.get(item["拍摄日编号"])
            if fix:
                for field in BATCH_EDITABLE_FIELDS:
                    if field in fix:
                        item["values"][field] = fix[field]
            retried += 1
            item.update(self._dispatch_one(item["values"], batch["批次号"]))
        _refresh_batch_counts(batch)
        if retried == 0:
            return batch, f"批次 {batch_no} 没有失败项需要重试", True
        return batch, _batch_message(batch), batch["failed"] == 0

    def _dispatch_one(self, item: dict[str, Any], batch_no: str) -> dict[str, Any]:
        """校验并生成一条通告单；失败时只记录原因，不影响同批其他拍摄日。"""
        values = {
            "拍摄日编号": str(item.get("拍摄日编号") or "").strip(),
            "集合时间": str(item.get("集合时间") or "").strip(),
            "拍摄地点": str(item.get("拍摄地点") or "").strip(),
            "出勤人员": str(item.get("出勤人员") or "").strip(),
            "用车安排": str(item.get("用车安排") or "").strip(),
        }
        result: dict[str, Any] = {
            "拍摄日编号": values["拍摄日编号"],
            "ok": False,
            "message": "",
            "通告编号": None,
            "entry_id": None,
            "values": values,
        }
        problems = _validate_dispatch(values)
        day = _find_shooting_day(values["拍摄日编号"]) if values["拍摄日编号"] else None
        if values["拍摄日编号"] and day is None:
            problems.append(f"拍摄日 {values['拍摄日编号']} 不存在")
        if problems:
            result["message"] = "；".join(problems)
            return result
        if _day_already_dispatched(values["拍摄日编号"]):
            result["message"] = "该拍摄日已生成通告单，未重复创建"
            return result
        entry = self._create_dispatch_entry(day, values, batch_no)
        result.update({
            "ok": True,
            "message": f"通告单 {entry['通告编号']} 已生成并下发",
            "通告编号": entry["通告编号"],
            "entry_id": entry["id"],
        })
        return result

    def _create_dispatch_entry(
        self,
        day: dict[str, Any],
        values: dict[str, str],
        batch_no: str,
    ) -> dict[str, Any]:
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["通告编号"] = _next_notice_no(rows)
        entry["拍摄日期"] = day.get("拍摄日期")
        entry["集合时间"] = values["集合时间"]
        entry["拍摄地点"] = values["拍摄地点"]
        entry["拍摄场次"] = day.get("计划场次")
        entry["出勤人员"] = values["出勤人员"]
        entry["用车安排"] = values["用车安排"]
        entry["通告状态"] = "已下发"
        entry["拍摄日编号"] = day.get("拍摄日编号")
        entry["批次号"] = batch_no
        entry["status"] = "已下发"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry
