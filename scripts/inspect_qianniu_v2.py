"""检查千牛 Excel v2（含确认收货时间列）的字段顺序与样本"""
import openpyxl
import json

src = r"C:\Users\18308\xwechat_files\wxid_o9xstzs3hi5a22_3c22\msg\file\2026-05\ExportOrderList26355889926(1).xlsx"
wb = openpyxl.load_workbook(src, read_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))

out = {
    "sheet": ws.title,
    "total_rows": len(rows),
    "headers": list(rows[0]) if rows else [],
    "samples": [[str(c) if c is not None else None for c in r] for r in rows[1:8]],
    "status_distribution": {},
    "shop_distribution": {},
    "payment_distribution": {},
}
if len(rows) > 1:
    statuses, shops, payments = {}, {}, {}
    headers_list = list(rows[0])
    status_idx = headers_list.index("订单状态") if "订单状态" in headers_list else 4
    shop_idx = headers_list.index("店铺名称") if "店铺名称" in headers_list else 6
    detail_idx = headers_list.index("支付详情") if "支付详情" in headers_list else 2
    for r in rows[1:]:
        s = r[status_idx] if len(r) > status_idx else None
        statuses[str(s)] = statuses.get(str(s), 0) + 1
        sp = r[shop_idx] if len(r) > shop_idx else None
        shops[str(sp)] = shops.get(str(sp), 0) + 1
        pd = r[detail_idx] if len(r) > detail_idx else ""
        if "微信支付" in str(pd):
            payments["wechat"] = payments.get("wechat", 0) + 1
        elif "支付宝" in str(pd):
            payments["alipay"] = payments.get("alipay", 0) + 1
        else:
            payments["other"] = payments.get("other", 0) + 1
    out["status_distribution"] = statuses
    out["shop_distribution"] = shops
    out["payment_distribution"] = payments

dst = r"D:\github-team\finance-system\scripts\qianniu_sample_v2.json"
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)
print(f"OK headers={len(out['headers'])} cols, total_rows={len(rows)}")
