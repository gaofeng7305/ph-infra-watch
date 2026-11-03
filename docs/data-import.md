# 批量导入指南

批量导入只接受人工提供的 CSV 或 JSON。工具不会生成项目/企业名称、ID、金额、容量、采购记录或证据，也不会覆盖已有记录。所有导入记录强制设为 `pending_review`；输入中的核验状态、核验人和核验时间不会保留。

## 支持的数据类型

`projects`、`companies`、`relationships`、`opportunities`。每行/对象必须提供人工分配的稳定 ID，以及至少一条证据：

```json
{
  "project_id": "人工分配的唯一 ID",
  "name": "来源支持的项目名称",
  "sector": "energy",
  "island_group": "Luzon",
  "evidence": [
    {
      "url": "https://source.example/path",
      "source_name": "来源机构",
      "published_at": null,
      "observed_at": "2026-11-03T00:00:00Z",
      "quote_or_fact": "来源中支持项目名称和行业的原文或准确摘录",
      "supports_fields": ["name", "sector"]
    }
  ]
}
```

上面是字段格式示例，不是实际项目数据。项目坐标必须在证据 `supports_fields` 中包含 `coordinates`；没有坐标证据就应省略 `coordinates`。可用 `island_group` 值为 `Luzon`、`Visayas`、`Mindanao`；没有可靠依据时省略，不猜测岛群。

JSON 可使用对象数组，或 `{ "projects": [ ... ] }` 等带类型键的形式。CSV 的列名使用 JSON 对象中的字段名；`evidence`、`coordinates`、`capacity`、`budget`、`aliases`、`company_ids`、`risks`、`next_checks` 等复合字段须在单元格内放置合法 JSON。

## 运行

在项目根目录执行：

```powershell
python scripts/import_data.py --type projects --input D:\path\to\your-records.json
python scripts/import_data.py --type companies --input D:\path\to\your-companies.csv
python scripts/import_data.py --type relationships --input D:\path\to\your-relationships.json
python scripts/import_data.py --type opportunities --input D:\path\to\your-opportunities.csv
```

也可用 `--format json` 或 `--format csv` 覆盖自动格式识别。

导入会校验 ID 唯一、字段白名单、HTTPS 证据链接、证据摘录、`supports_fields`、项目/企业关联和坐标证据。任何一条记录不合格时整批拒绝，不写入任何新记录。成功后先运行：

```powershell
python scripts/validate_data.py
python scripts/check_site.py
python scripts/check_snapshot.py
```

核验人员须打开证据原文检查每条字段，并在手工审阅后更新 JSON 中的 `verification_status`、`verified_by`、`verified_at`。导入成功不等于项目/企业已被核实。
