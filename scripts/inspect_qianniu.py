"""一次性脚本：读千牛 Excel 样例，把字段+样本写到 UTF-8 文件给 PM 审视"""
import openpyxl
import json
import sys

src = r"C:\Users\18308\xwechat_files\wxid_o9xstzs3hi5a22_3c22\msg\file\2026-04\ExportOrderList26416386484(1).xlsx"
wb = openpyxl.load_workbook(src, read_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))

out = {
    "sheet": ws.title,
    "total_rows": len(rows),
    "headers": list(rows[0]) if rows else [],
    "samples": [[str(c) if c is not None else None for c in r] for r in rows[1:6]],
    "status_distribution": {},
}
if len(rows) > 1:
    statuses = {}
    for r in rows[1:]:
        s = r[4] if len(r) > 4 else None
        statuses[str(s)] = statuses.get(str(s), 0) + 1
    out["status_distribution"] = statuses

dst = r"D:\github-team\finance-system\scripts\qianniu_sample.json"
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)
print(f"OK total_rows={len(rows)}")
