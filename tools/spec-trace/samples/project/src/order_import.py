"""受注ファイル取込（サンプル実装）."""

from __future__ import annotations


class OrderValidator:
    def validate(self, row: dict) -> list[str]:
        errors = []
        if not row.get("order_no"):
            errors.append("order_no は必須")
        if int(row.get("quantity") or 0) < 1:
            errors.append("quantity は 1 以上")
        return errors


def import_orders(rows: list[dict], table: dict) -> int:
    added = 0
    for row in rows:
        if row["order_no"] in table:
            continue  # 冪等: 既にあれば登録しない
        table[row["order_no"]] = row
        added += 1
    return added
