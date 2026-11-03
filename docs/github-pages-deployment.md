# GitHub Pages 正式部署操作指南

本项目为静态 HTML/CSS/JavaScript 网站；Python 采集器由 GitHub Actions 运行，生成 JSON 后一并发布。当前 D 盘项目没有 Git 仓库或 GitHub 远端，需先完成下列一次性设置。

## 1. 创建并推送 GitHub 仓库

在 GitHub 创建空仓库，然后在 PowerShell 中进入项目根目录：

```powershell
cd D:\PH-Infra-Watch-Development
git init -b main
git add .
git commit -m "Initial PH Infra Watch release"
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

将 `OWNER/REPOSITORY` 替换为实际仓库路径。首次推送前确认代码和 `site/data/data.json` 不含 API Key。不要把密钥写入 JSON、工作流文件、HTML/JavaScript 或 Git 历史。

## 2. 配置 Actions 和 Pages

1. 仓库 **Settings → Actions → General → Workflow permissions**：允许工作流读写仓库内容；工作流用 `contents: write` 提交采集快照。
2. **Settings → Pages → Build and deployment**：将 Source 设为 **GitHub Actions**。
3. 如果 `main` 有分支保护规则，允许 `github-actions[bot]` 更新 `site/data/data.json`。否则快照提交步骤会失败并阻止该轮部署。
4. 部署任务按 Pages artifact 流程使用 `pages: write` 和 `id-token: write`，不需要把仓库设为公开。GitHub 官方要求参见[自定义工作流文档](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。

## 3. 配置可选 AI

不开 AI 时无需配置任何 Secret，采集、筛选、地图、人工记录和规则评分照常运行。

若确需启用：

1. **Settings → Secrets and variables → Actions → New repository secret**，名称设为 `OPENAI_API_KEY`，值粘贴在 Secret 输入框。
2. 可选地在 **Variables** 新增 `OPENAI_MODEL`；不设置则采用代码默认模型。
3. Key 仅供 Actions 中 Python 采集步骤使用，不进入浏览器端。AI 返回仍需人工核实，且会标记为 AI 辅助内容。

## 4. 手动发布及检查

1. **Actions → Collect and publish PH Infra Watch → Run workflow**，选择 `main` 分支运行。
2. 检查 Validate、Python tests、Node map-filter tests、RSS collection、snapshot check、保存快照及 Deploy Pages 各步骤。
3. RSS 全部失败时工作流会失败，不会部署该次失败构建，上一版网站继续服务；部分来源失败会发布状态提示并保留历史线索。
4. 打开工作流生成的 Pages URL，检查六个页面、地图署名、手机宽度布局、数据更新时间、证据链接以及 AI 关闭时的提示。

之后工作流还会在每天 UTC 00/06/12/18 定时执行。GitHub 可能延迟定时任务；首次上线后应每日检查 Actions 运行状态和 RSS 来源健康信息。

## 5. 人工数据导入

先根据[批量导入指南](data-import.md)整理带来源证据的 JSON 或 CSV；在本地运行导入器和校验器，将 JSON 变更审阅后再提交推送。导入默认待审核，不会把新闻线索自动升级为真实项目或已确认机会。
