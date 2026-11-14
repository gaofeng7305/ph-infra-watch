# PH Infra Watch

菲律宾通信与能源项目情报网站一期。静态 HTML/CSS/JavaScript 前端，Python 标准库负责 RSS 发现、数据校验和可选 AI 辅助，JSON 作为一期数据存储，GitHub Actions 构建并部署 GitHub Pages。

## 当前数据状态

初始安装不含人工维护的真实项目、企业、关系或商业机会。采集器会从 RSS 生成新闻线索；它们均为未核验记录，不等于正式项目、招标或商业机会。只有具备字段级证据并经人工审核的记录才能标记为已核验。空项目库表示尚无已录入项目，不代表菲律宾没有相关项目。

## 页面

- `site/index.html`：Dashboard 总览与数据状态
- `site/intelligence.html`：新闻及行业动态线索
- `site/projects.html`：项目档案和人工核验状态
- `site/map.html`：Leaflet 项目地图及列表回退
- `site/companies.html`：企业档案和项目关系
- `site/opportunities.html`：规则分析与可选 AI 机会建议

## 行业动态显示

`site/intelligence.html` 使用紧凑新闻列表和客户端分页。标题长度（默认 30 字符）、每页数量（默认 20）、中文副标题显示及新旧排序保存在浏览器 local storage 中。搜索和现有筛选先于分页执行；完整英文标题可通过桌面键盘/鼠标提示或移动端展开按钮查看。

## 本地运行

Python 3.10+，无需第三方 Python 包。运行 JavaScript 地图逻辑测试需 Node.js（网站本身不依赖 Node 运行时）。

```powershell
python -m unittest discover -s tests -v
node --check site/assets/app.js
node --check site/assets/map-logic.js
node --test tests/test_map_logic.cjs
python scripts/validate_data.py
python scripts/check_site.py
python -m http.server 8000 --directory site
```

浏览器访问 `http://localhost:8000`。地图依赖 Leaflet CDN 和 OpenStreetMap 标准瓦片；二者不可用时，项目表格仍可操作。

## 配置数据源

`config/sources.json` 中提供 9 组 Google News RSS 搜索主题。脚本运行时逐源请求并记录成功/失败；公共 RSS 的可达性、内容覆盖、访问限制和许可可能变化，不能将其视为官方完整数据源。正式运营前应逐源复核条款和可用性。官方机构链接仅作人工核验入口。

采集命令：

```powershell
python scripts/collect.py
```

本地运行采集器会更新本地快照，不会自动推送。GitHub Actions 在采集、快照校验通过后，将 `site/data/data.json` 提交回当前分支，再上传整个 `site/` 目录为 Pages artifact 并部署。全源失败会使构建失败并停止部署；单个源失败会保留历史线索并记录部分失败状态。

## 人工核验

人工维护：

- `config/manual_projects.json`
- `config/manual_companies.json`
- `config/manual_relationships.json`
- `config/manual_opportunities.json`

字段说明、证据格式和审核步骤见 [`docs/data-model-and-review.md`](docs/data-model-and-review.md)。

项目状态为 `pending_review`、`verified` 或 `needs_review`。设为 `verified` 必须填写 `verified_by`、`verified_at`，并提供 HTTPS 证据链接。关系和机会也必须绑定证据。审核仅适用于证据支持的字段；未知值留空。更新配置后运行 `python scripts/validate_data.py`。

## 可选 OpenAI 辅助

没有 `OPENAI_API_KEY` 时，构建、采集、规则机会分析和网站均正常运行。可在本地环境变量或 GitHub Actions Secret 中配置 `OPENAI_API_KEY`，并可设置 `OPENAI_MODEL`（默认 `gpt-4.1-mini`）及 `AI_MAX_RECORDS`（默认 10）。AI 只生成摘要/分析草稿，不核实事实，也不自动把项目改为 `verified`。密钥不得写进仓库或前端。

```powershell
$env:OPENAI_API_KEY = "在本机安全设置"
python scripts/collect.py
```

GitHub 仓库中进入 Settings → Secrets and variables → Actions，新增 `OPENAI_API_KEY`。调用会产生 API 用量费用；未设置时跳过 AI。

采集会优先处理当前快照中最新的新闻记录，并在 `scripts/data/title_translation_cache.json` 持久保存成功的标题翻译，以复用相同标题结果。失败的翻译不会写入缓存，可在后续任务重试。可使用 `python scripts/backfill_title_zh.py --limit 10` 对历史新闻分批补译；每次最多 50 条，只更新缺失翻译，脚本可重复运行以继续处理。没有 API key 时脚本不会调用 API 或写入快照。缓存和新闻数据都应与代码一起提交，GitHub Actions 会提交自动采集产生的更新。

## GitHub Pages

仓库推送到 GitHub 后，在 Settings → Pages 将 Build and deployment 的 Source 设为 GitHub Actions。`.github/workflows/publish.yml` 同时支持手动运行和每日定时采集。工作流为 Pages 授予最小所需 `pages: write` 和 `id-token: write` 权限。初次部署需要由仓库管理员在 GitHub 上启用 Pages；此代码仓库本身不会自动创建远程仓库或发布网站。

## 数据合规和安全

- 保留来源 URL、发布/发现/核验时间；默认只保存 RSS 的标题、短摘要和元数据。
- 仅 HTTPS 外链；动态内容作为文本转义，不直接注入不可信 HTML。
- 不抓取需要登录或绕过限制的内容，不批量下载地图瓦片。
- OpenStreetMap 标准瓦片为尽力服务，须保留可见归属并遵守其使用政策；商业或高流量使用前选择许可合适的瓦片服务商。
- 平台为非官方公开信息整理工具，商业及投标行动以最新官方文件为准。

## 关键第三方文档

- [Leaflet Quick Start](https://leafletjs.com/examples/quick-start/)：当前固定使用 Leaflet 1.9.4。
- [OpenStreetMap Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)：生产使用前需再次核对服务政策和流量是否适用。
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)：工作流按 Pages artifact 部署方式配置。
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)：仅在配置密钥后调用，API schema、模型和用量以部署时的官方文档/账号配置为准。

## 目录

```text
config/                 数据源和人工维护记录
scripts/                采集、校验、机会分析
site/                   六个页面、静态资源、JSON 数据
tests/                  离线单元测试
.github/workflows/      GitHub Pages 构建与部署
```
## 批量导入

参阅[批量导入指南](docs/data-import.md)，通过证据校验的 JSON/CSV 导入人工提供的数据；只追加，不覆盖，默认待审核。

## GitHub Pages 上线

参阅[正式部署操作指南](docs/github-pages-deployment.md)。
