# PH Infra Watch 1.5 最后一轮上线前完善记录

**目标目录：** `D:\PH-Infra-Watch-Development`  
**完成日期：** 2026-11-03  
**状态：** 本地开发与测试通过，可进入 GitHub 仓库设置及上线流程。没有创建 GitHub 仓库或执行公网发布。

## 已完成的五项工作

### 项目地图

- 地图增加 Luzon、Visayas、Mindanao 筛选及可点击的区域项目计数。
- 增加通信、能源、基础设施/综合分类和已核验/未核验状态筛选；筛选条件可组合。
- 地图标记点击后显示项目名称、分类、岛群、核验状态、描述和来源链接。
- 仅当坐标值有效、HTTPS 证据摘录支持 `coordinates` 时才绘制标记；岛群计数也只使用来源明确支持的 `island_group`。不会从省名推断岛群，不会补造坐标。
- 保留 OpenStreetMap 可见署名、瓦片政策和问题报告链接。手机浏览器视口实测为 390×844：页面宽度无溢出，地图容器 307×390 px。

### 商业机会评分

采集时为机会计算 0–100 情报跟进优先级，展示各项得分、满分、依据和更新时间：

| 维度 | 满分 |
|---|---:|
| 证据完整度 | 35 |
| 商业需求明确度 | 30 |
| 项目阶段/采购相关性 | 20 |
| 信息时效性 | 15 |

每个来源域名最多贡献 5 分的来源分，字段证据最多贡献 20 分；少于两个不同来源域名时总分上限 45。没有已核验项目档案时总分上限 30。采购得分仅检查原始证据中的需求信息，不从 AI 摘要或机会文案加分；明确否定采购的信息不计需求/采购分。页面注明分数只用于跟进优先级，不代表项目真实性或成交概率。评分不改变核验状态。

### AI 内容标识和证据边界

- RSS 原始标题/摘要与 AI 摘要、候选实体/地点分开显示。
- 所有 AI 内容标“AI辅助生成”或“AI辅助推测（未核验）”，候选企业/地点仅保留原始标题或摘要中逐字可找到的值，并附来源链接及支持字段证据。
- AI JSON Schema 不提供金额、容量或采购需求字段；快照检查会拒绝这些未经授权的 AI 事实字段。AI 不能修改核验状态。
- 未配置 API Key 的完整 RSS 运行成功，AI 状态是 `disabled`。

### 数据批量导入

- 新增本地命令行 JSON/CSV 批量导入，可处理项目、企业、企业关系和商业机会。
- 只接受人工提供的数据，不生成 ID 或实体；仅追加，不覆盖。无论输入状态如何，导入都强制设为 `pending_review`。
- 校验字段白名单、唯一 ID、HTTPS 证据链接、摘录、支持字段、外键和坐标证据；整批任一行失败则不写入。
- 导入命令、JSON/CSV 格式和审核步骤见 [data-import.md](data-import.md)。证据链接做格式和 HTTPS 校验；导入器不会自动访问任意外部 URL，仍须由核验人打开原文确认。

## 修改文件清单

- 地图/机会 UI：`site/map.html`、`site/opportunities.html`、`site/assets/map-logic.js`、`site/assets/app.js`、`site/assets/styles.css`。
- 机会评分与快照校验：`scripts/opportunity_scoring.py`、`scripts/collect.py`、`scripts/check_snapshot.py`。
- AI 证据约束和项目校验：`scripts/ai_assist.py`、`scripts/validate_data.py`。
- JSON/CSV 导入：`scripts/import_data.py`。
- 测试/自动化：`tests/test_pipeline.py`、`tests/test_map_logic.cjs`、`.github/workflows/publish.yml`。
- 操作文档：`docs/data-import.md`、`docs/github-pages-deployment.md`、`docs/data-model-and-review.md`、`README.md`。

## 测试报告

所有命令均在 `D:\PH-Infra-Watch-Development` 实际运行。

| 检查 | 结果 |
|---|---|
| `python -m unittest discover -s tests -v` | 23/23 通过。上一轮 17 项既有测试保留；新增 AI 来源约束、评分边界、JSON/CSV 导入与待审核状态测试。 |
| `node --test tests/test_map_logic.cjs` | 3/3 通过：岛群统计/筛选、行业与核验状态组合、坐标证据门槛。 |
| `node --check site/assets/app.js` 和 `map-logic.js` | 通过。 |
| `python scripts/validate_data.py` | 通过。 |
| `python scripts/check_site.py` | 6 个页面通过。 |
| `python scripts/check_snapshot.py` | 通过。 |
| 无 API Key 的实际 RSS 采集 | 9/9 请求成功；生成 438 条历史新闻线索；AI disabled。最新生成时间 `2026-11-03T13:43:26Z`。 |
| 窄屏页面浏览器复查 | 390×844 无横向溢出，地图和底图署名加载；三种筛选控件可操作。 |

各来源实际状态：`market-energy` 80、`market-power` 78、`market-procurement` 2、`market-telecom` 10、`news-dict` 90、`news-doe` 59、`news-doe-new` 0、`news-philgeps` 3、`news-ppp` 29。`news-doe-new` 是请求成功但本次零结果。

## 真实数据状态与范围

当前没有人工项目、企业、关系或机会记录。因而地图区域统计为 0，正式机会页面没有可展示的实际评分卡。评分及导入已用测试数据验证算法/校验边界，但没有写入任何虚构项目、企业、招标或容量到生产 JSON。

AI 未配置密钥，真实 API 响应未调用；AI 字段处理、原文匹配和证据约束由本地模拟响应测试覆盖。启用 AI 前应按 [GitHub Pages 部署指南](github-pages-deployment.md) 添加 Secret，之后人工复核实际模型结果。

## GitHub 正式部署

项目目录当前没有 `.git` 或远端仓库，所以没有声称 GitHub Actions/Pages 已经实测上线。按[正式部署操作指南](github-pages-deployment.md)完成仓库初始化、`main` 推送、Actions 内容写入权限、Pages 选择 GitHub Actions、可选 Secret 设置，再手动运行 `Collect and publish PH Infra Watch`。应确认 Python 测试、Node 地图测试、RSS、快照校验和 Pages 部署全部通过后再宣布上线。
