"""拍摄通告业务规则：状态流转、字段校验与批量下发都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "notice"
SHOOTING_MODULE = "shooting"
REQUIRED_FIELDS = ["通告编号", "拍摄日期", "集合时间"]
# 批量下发按拍摄日逐条生成通告单，每条都要单独过一遍这三类校验。
BATCH_REQUIRED_FIELDS = ["拍摄日期", "集合时间", "拍摄地点", "出勤人员"]
BATCH_OPTIONAL_FIELDS = ["拍摄场次", "用车安排", "拍摄日编号", "client_key"]
STATUS_ORDER = ["待下发", "已下发", "执行中", "已完成"]
ACTION_RULES = {"下发通告": "已下发", "开始执行": "执行中", "确认完成": "已完成"}
NEGATIVE_ACTIONS = []
BATCH_NO_PREFIX = "BAT-NOTI-"


class NoticeService:
    def __init__(self) -> None:
        # 批次记录不落库，跟示例数据一样放内存里，按批次号查看结果。
        self._batches: dict[str, dict[str, Any]] = {}

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        batch_no: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通告编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if batch_no:
            rows = [row for row in rows if row.get("批次编号") == batch_no]
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
        entry = {"id": self._next_id(rows)}
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

    # ------------------------------------------------------------------
    # 批量下发
    # ------------------------------------------------------------------
    def dispatch_batch(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """按拍摄日批量下发通告：逐条校验、逐条生成，整组失败不影响已成功的项。"""
        items = self._extract_items(payload)
        if items is None:
            return None, "批量下发需要提供 items 条目列表"
        if not items:
            return None, "至少选择一个拍摄日才能批量下发"

        batch_no = str(payload.get("batch_no") or "").strip()
        if batch_no:
            existing = self._batches.get(batch_no)
            if existing is not None:
                # 同批数据重复提交直接回放上次结果，不再重复创建通告单。
                return existing, f"批次 {batch_no} 已提交过，返回原有批次结果，未重复创建"
        else:
            batch_no = self._next_batch_no()

        results, success_count, failure_count = self._process_items(batch_no, items)
        batch = {
            "batch_no": batch_no,
            "total": len(results),
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._batches[batch_no] = batch
        return batch, self._batch_message(batch, created=True)

    def retry_batch(self, batch_no: str, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """只重试指定批次中失败的通告；成功的项原样保留，不重复创建。"""
        batch = self._batches.get(batch_no)
        if batch is None:
            return None, f"批次 {batch_no} 不存在，无法重试；请先发起批量下发"

        items = self._extract_items(payload)
        if items:
            # 允许在重试时修正集合时间、地点、出勤人员等错误数据；不传则沿用原始提交。
            by_key = {self._item_key(item): item for item in items}
            pending = []
            for result in batch["results"]:
                if result.get("ok"):
                    continue
                key = result.get("client_key")
                if key and key in by_key:
                    merged = {field: result.get("submitted", {}).get(field) for field in BATCH_REQUIRED_FIELDS + BATCH_OPTIONAL_FIELDS}
                    merged.update(by_key[key])
                    merged["client_key"] = key
                    pending.append(merged)
                else:
                    pending.append(result.get("submitted") or {})
        else:
            pending = [result.get("submitted") or {} for result in batch["results"] if not result.get("ok")]

        if not pending:
            return batch, f"批次 {batch_no} 没有失败项，无需重试"

        results, success_count, failure_count = self._process_items(batch_no, pending)
        # 用本轮处理结果替换掉旧的失败项；成功项（含更早轮次成功的）继续保留。
        fresh_by_key = {result.get("client_key"): result for result in results}
        merged_results = []
        for result in batch["results"]:
            if result.get("ok"):
                merged_results.append(result)
            else:
                merged_results.append(fresh_by_key.get(result.get("client_key"), result))
        # 重试时若修正数据带来了此前没有的新键，追加到结果末尾。
        known_keys = {result.get("client_key") for result in merged_results}
        for result in results:
            if result.get("client_key") not in known_keys:
                merged_results.append(result)

        batch["results"] = merged_results
        batch["success_count"] = sum(1 for result in merged_results if result.get("ok"))
        batch["failure_count"] = len(merged_results) - batch["success_count"]
        return batch, self._batch_message(batch, created=False)

    def get_batch(self, batch_no: str) -> dict[str, Any] | None:
        """返回列表后仍可按批次号回看本批成功与失败明细。"""
        return self._batches.get(batch_no)

    # ------------------------------------------------------------------
    # 内部规则
    # ------------------------------------------------------------------
    def _process_items(
        self, batch_no: str, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int, int]:
        rows = store.rows(MODULE)
        shooting_index = {
            str(day.get("拍摄日编号") or "").strip(): day
            for day in store.rows(SHOOTING_MODULE)
        }
        seen_keys: set[str] = set()
        results: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for index, raw in enumerate(items, start=1):
            item = self._normalize_item(raw)
            client_key = item.get("client_key") or f"第{index}条"
            # 组内同一拍摄日重复出现时只生成一张通告单，重复项按失败处理。
            if client_key in seen_keys:
                failure_count += 1
                results.append(self._failure(client_key, item, f"组内存在重复的拍摄日「{client_key}」，已拦截"))
                continue
            seen_keys.add(client_key)

            errors = self._validate_item(item, shooting_index)
            if errors:
                failure_count += 1
                results.append(self._failure(client_key, item, "；".join(errors)))
                continue

            entry = {
                "id": self._next_id(rows),
                "通告编号": self._next_notice_no(rows),
                "拍摄日期": item["拍摄日期"],
                "集合时间": item["集合时间"],
                "拍摄地点": item["拍摄地点"],
                "拍摄场次": item.get("拍摄场次") or "",
                "出勤人员": item["出勤人员"],
                "用车安排": item.get("用车安排") or "",
                "通告状态": STATUS_ORDER[1],
                "批次编号": batch_no,
                "明细键": client_key,
                "status": STATUS_ORDER[1],
                "pending": STATUS_ORDER[1] != STATUS_ORDER[-1],
                "abnormal": False,
            }
            rows.append(entry)
            success_count += 1
            results.append({
                "ok": True,
                "client_key": client_key,
                "拍摄日编号": item.get("拍摄日编号") or "",
                "拍摄日期": item["拍摄日期"],
                "集合时间": item["集合时间"],
                "拍摄地点": item["拍摄地点"],
                "出勤人员": item["出勤人员"],
                "message": "通告单已下发",
                "entry_id": entry["id"],
                "通告编号": entry["通告编号"],
                "submitted": item,
            })
        return results, success_count, failure_count

    def _validate_item(
        self, item: dict[str, Any], shooting_index: dict[str, dict[str, Any]]
    ) -> list[str]:
        """集合时间、地点、出勤人员分别校验，问题一次性列全，便于逐项修正。"""
        errors: list[str] = []

        missing = [field for field in BATCH_REQUIRED_FIELDS if not str(item.get(field) or "").strip()]
        if missing:
            errors.append(f"缺少必填字段：{'、'.join(missing)}")

        shooting_date = str(item.get("拍摄日期") or "").strip()
        if shooting_date and not self._parse_date(shooting_date):
            errors.append("拍摄日期格式应为 YYYY-MM-DD")

        call_time = str(item.get("集合时间") or "").strip()
        if call_time and not self._parse_call_time(call_time):
            errors.append("集合时间应为 HH:MM 或 YYYY-MM-DD HH:MM 格式")

        attendance = str(item.get("出勤人员") or "").strip()
        if attendance and not self._split_persons(attendance):
            errors.append("出勤人员至少填写一人，多人请用逗号或顿号分隔")

        day_no = str(item.get("拍摄日编号") or "").strip()
        if day_no:
            day = shooting_index.get(day_no)
            if day is None:
                errors.append(f"拍摄日编号「{day_no}」在拍摄进度中不存在")
            elif shooting_date and str(day.get("拍摄日期") or "").strip() != shooting_date:
                errors.append(
                    f"拍摄日期 {shooting_date} 与拍摄日 {day_no} 的排期 {day.get('拍摄日期')} 不一致"
                )
        return errors

    @staticmethod
    def _normalize_item(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        item = {field: raw.get(field) for field in BATCH_REQUIRED_FIELDS + BATCH_OPTIONAL_FIELDS}
        item = {key: value for key, value in item.items() if value not in (None, "")}
        day_no = str(item.get("拍摄日编号") or "").strip()
        date_value = str(item.get("拍摄日期") or "").strip()
        if not item.get("client_key"):
            item["client_key"] = day_no or date_value
        return item

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
        items = payload.get("items")
        if items is None:
            return None
        if not isinstance(items, list):
            return None
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _item_key(item: dict[str, Any]) -> str:
        return str(item.get("client_key") or item.get("拍摄日编号") or item.get("拍摄日期") or "").strip()

    @staticmethod
    def _failure(client_key: str, item: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "client_key": client_key,
            "拍摄日编号": item.get("拍摄日编号") or "",
            "拍摄日期": item.get("拍摄日期") or "",
            "集合时间": item.get("集合时间") or "",
            "拍摄地点": item.get("拍摄地点") or "",
            "出勤人员": item.get("出勤人员") or "",
            "message": message,
            "entry_id": None,
            "通告编号": None,
            "submitted": item,
        }

    @staticmethod
    def _split_persons(attendance: str) -> list[str]:
        for separator in ["，", "、", ";", "；", "/"]:
            attendance = attendance.replace(separator, ",")
        return [name.strip() for name in attendance.split(",") if name.strip()]

    @staticmethod
    def _parse_date(value: str) -> bool:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False
        return True

    @staticmethod
    def _parse_call_time(value: str) -> bool:
        for pattern in ("%H:%M", "%Y-%m-%d %H:%M"):
            try:
                datetime.strptime(value, pattern)
                return True
            except ValueError:
                continue
        return False

    def _next_batch_no(self) -> str:
        max_seq = 0
        for number in self._batches:
            if number.startswith(BATCH_NO_PREFIX):
                suffix = number.removeprefix(BATCH_NO_PREFIX)
                if suffix.isdigit():
                    max_seq = max(max_seq, int(suffix))
        return f"{BATCH_NO_PREFIX}{max_seq + 1:04d}"

    @staticmethod
    def _next_id(rows: list[dict[str, Any]]) -> int:
        return max((int(row.get("id", 0)) for row in rows), default=0) + 1

    @staticmethod
    def _next_notice_no(rows: list[dict[str, Any]]) -> str:
        max_seq = 0
        for row in rows:
            number = str(row.get("通告编号") or "")
            if number.startswith("NOTI-"):
                suffix = number.removeprefix("NOTI-")
                if suffix.isdigit():
                    max_seq = max(max_seq, int(suffix))
        return f"NOTI-{max_seq + 1:04d}"

    @staticmethod
    def _batch_message(batch: dict[str, Any], *, created: bool) -> str:
        action = "批量下发完成" if created else "失败项重试完成"
        if batch["failure_count"] == 0:
            return f"{action}：{batch['success_count']} 条通告全部下发成功"
        return (
            f"{action}：成功 {batch['success_count']} 条，失败 {batch['failure_count']} 条，"
            "可仅重试失败通告"
        )
