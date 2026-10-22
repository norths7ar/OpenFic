# OpenFic 个人小说协作分支

![OpenFic Banner](./banner.svg)

OpenFic 是用于本地管理多本小说的写作工作台，支持设定、提纲、正文、讨论会话与 AI 辅助创作。

## 主要能力

- 以项目隔离小说资料、会话和待审变更。
- 管理背景设定、角色、提纲、笔记、章节和文档历史。
- 在讨论、规划与创作流程中按资料可见性提供上下文。
- 将 AI 产出以草稿或待审变更的形式交给作者采用。
- 在 OpenFic 项目资料包与声明式 Markdown 源包之间往返资料。

## 文档

- [CHANGELOG.md](./CHANGELOG.md)：已发布与待发布的用户可感知变化。
- [backend/README.md](./backend/README.md)：后端开发入口。
- [docs/openfic-import.example.yaml](./docs/openfic-import.example.yaml)：Markdown 源包映射示例。
- [AGENTS.md](./AGENTS.md)：仓库协作与部署规则。

## 目录分工

| 目录 | 用途与保留规则 |
| --- | --- |
| `data/` | 本机正式服务的数据、配置、日志与运行状态，按私有数据保护。 |
| `backend/` | FastAPI 后端与 Python 打包入口；`backend/data/` 保留现有验证副本，不是本机正式数据盘。 |
| `frontend/` | 网页界面源码与构建配置。 |
| `scripts/` | 本地服务管理、备份恢复与开发检查脚本。 |
| `docs/` | 少量维护文档与资料交换示例。 |
| `output/` | 需要保留的产物；`backups/` 保存备份，`reports/` 保存审查与验证报告，不按临时文件清理。 |
| `tmp/` | 可丢弃的临时工作文件；历史遗留的私有原稿和备份须明确保护，清理前逐项确认，不得整目录删除。 |

测试清理阶段的报告及配套数据归档在 [output/reports/test-audit/测试逐项审查.html](./output/reports/test-audit/测试逐项审查.html)，属于当时的决策快照，不是实时测试清单。验证日志和截图归档在 `output/reports/validation/`。这些本地产物不纳入 Git，新克隆的仓库不会自带。

`.venv/`、`node_modules/` 和 `frontend/dist/` 虽可重建，但分别用于运行、开发和正式网页加载，不作为日常缓存清理。

## 本地运行

正式服务运行在 Windows，地址为 <http://127.0.0.1:18081/>，由后端同时提供构建后的网页与 API，健康检查为 <http://127.0.0.1:18081/api/v1/health>。

使用 PowerShell 7.4+、Python 3.12/3.13、uv 和 pnpm。首次准备环境并构建网页：

```powershell
cd backend
uv sync --frozen
cd ../frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
```

后端的 `deployment` 依赖组包含 `langchain-deepseek>=1.0.1`，`tool.uv.default-groups = ["dev", "deployment"]` 使普通 `uv sync` 也默认安装并保留部署依赖。原有 provider extras 保留；本机部署所需的 SDK 统一加入 `deployment` 组。

在 `backend/` 中添加或移除部署 SDK，例如：

```powershell
uv add --group deployment langchain-anthropic
uv remove --group deployment langchain-anthropic
```

按需执行对应命令，并将 `backend/pyproject.toml` 与 `backend/uv.lock` 一起提交，后续安装和重建即可恢复相同的部署依赖。开发检查使用 `uv run --no-sync ...`。

在仓库根目录管理服务：

```powershell
./scripts/openfic-service.ps1 start
./scripts/openfic-service.ps1 status
./scripts/openfic-service.ps1 logs
./scripts/openfic-service.ps1 restart
./scripts/openfic-service.ps1 stop
```

服务数据位于仓库根目录的 `data`，本机路径为 `E:\Projects\novel\OpenFic\data`。日志在 `data/logs`，运行状态在 `data/runtime/openfic.json`。

服务管理脚本通过 `OPENFIC_DATA_DIR` 指定数据目录。未设置该变量时，使用 CLI（`openfic serve`）启动默认使用用户目录下的 `~/.openfic`；绕过 CLI、直接加载后端应用时才回退到 `backend/data/`。`backend/data/` 及现有数据继续保留，独立运行后端时应明确选择数据目录。

日常写作无需重新构建。纯前端代码更新后，在 `frontend/` 执行 `pnpm build`；前端锁文件变化时，先执行 `pnpm install --frozen-lockfile` 再构建。仅修改后端 Python 源码时，完成检查后重启服务即可。正式网页使用当前服务地址访问 API，构建时保持 `VITE_BACKEND_URL` 未设置，以免连接到测试后端。隔离验证可用服务脚本的 `-DataPath` 和 `-Port` 指定独立数据目录与端口。

首次安装、重建 Python 环境或后端依赖声明／锁文件变化时，在 `backend/` 执行 `uv sync --frozen`，更新后按需重启后端。普通源码更新不升级依赖。

## 数据与资料交换

`data` 保存正式资料、提供商配置、会话记录和文档历史。正式资料以 SQLite 为准；浏览器草稿是未提交工作副本，API 缓存可刷新，LanceDB 是派生检索索引。正文与笔记保存会核对编辑基准，本地稿与正式内容都发生变化时，由作者比较并选择保留的版本。

### 应用完整备份与恢复

完整备份由服务端快照和浏览器伴随包组成。先停止编辑，在「设置 → 高级」导出浏览器伴随包，再执行：

```powershell
./scripts/openfic-service.ps1 backup -BrowserBackupPath "$HOME/Downloads/openfic-browser-backup-时间.json"
```

快照默认写入 `output/backups/`，包含数据目录、配置的外置数据、有效加密密钥、源码工作树、已有的网页构建产物和文件校验和。脚本会暂停受管理服务，备份结束后恢复原有运行状态。省略 `-BrowserBackupPath` 只能得到服务端备份，不能保存浏览器里的未提交工作；快照含小说内容与凭据，应作为私有数据保管。

伴随包保存导出所在浏览器档案和网站地址下的草稿、编辑状态及应用偏好，不包含其他浏览器档案或地址中的工作。

恢复会校验文件清单与校验和，目标必须是新目录：

```powershell
./scripts/openfic-service.ps1 restore -SnapshotPath ./output/backups/快照目录 -RestorePath ./output/restored-openfic
```

恢复后的 `source/` 保存对应源码，`data/` 和 `external/` 保存服务数据。从原仓库根目录进入恢复源码的 `source/backend/`，按锁文件重建依赖，再使用 `restore-environment.json` 启动独立实例：

```powershell
cd ./output/restored-openfic/source/backend
uv sync --frozen
cd ../../../..
./output/restored-openfic/source/scripts/openfic-service.ps1 start -DataPath ./output/restored-openfic/data -RestoreEnvironmentPath ./output/restored-openfic/restore-environment.json -Port 18082
```

用新浏览器档案打开恢复实例，在「设置 → 高级」导入快照中的 `browser.json` 并重新加载。导入要求该档案在此地址下没有现存项目、编辑状态或草稿；恢复的草稿仍需作者保存，不会自动覆盖正式正文。

### 文档历史与回收站

章节、背景设定、角色、提纲和笔记均支持文档历史。编辑器工具栏的「历史版本」可预览并恢复标题和正文，不改变当前文件夹或可见性。手工编辑按 5 分钟合并恢复点，每篇保留最近 100 个；导入覆盖、采用待审变更和恢复操作会在内容变化前单独留点。历史从功能启用后的修改开始记录。

删除条目后，可在标签栏右侧的「回收站」预览、恢复或永久删除。回收站不自动清空；恢复沿用原条目 ID，原文件夹或卷不存在时放回对应类型的根目录，ID 占用或角色、背景设定重名时会提示冲突。历史与回收站保存在数据库中，随完整备份保存，不包含在两类资料包中；永久删除回收站条目会清理其对应历史，删除项目会清理整个项目的记录。

### 项目资料交换

书架可导入和导出两类资料包，用于交换当前资料，不替代完整备份：

- **OpenFic 项目资料包**：保留资料、章节的对象 ID、顺序、可见性、文件夹、卷和基线信息，也导出讨论中的用户与助手文字。导入的讨论作为归档，不恢复可继续运行的 Agent 会话；全局配置、运行检查点和浏览器草稿仍需完整备份。
- **Markdown 源包**：在 ZIP 根目录使用 `openfic-import.yaml` v2 映射背景设定、角色、提纲、笔记和正文。映射根目录下的文件是根级条目，下一层目录表示文件夹或卷，支持单层目录归属。

Markdown 源包用 `<!-- openfic:item` 元数据块区分条目并保留稳定 ID，正文中的 Markdown 标题不参与拆分。文件名不决定身份，移动文件可以改变归属；重命名目录时同步修改 YAML 中的 `folders.source`，以保留文件夹身份。导出可选择每条目一文件或每目录合并一文件，具体配置及保留标记的转义方式见 [映射示例](./docs/openfic-import.example.yaml)。

导入前先生成预览，核对新增、更新与冲突后再应用。

### 导出到文档备份仓库

在 OpenFic 中写作、用独立 Git 仓库保存文档历史时，运行：

```powershell
./scripts/export-document-backup.ps1 -ProjectId '项目 ID' -Destination '../小说备份目录'
```

目标目录须已存在。脚本调用本机正式服务的 Markdown 源包 API，完整下载并解压后更新目标目录；可用 `-BaseUrl` 指定其他服务。根目录的 `.git`、`.gitignore`、`.gitattributes`、`archives`、`README` 和 `AGENTS`（包括带扩展名的名称，不区分大小写）保留，其余内容替换为本次导出。需要长期保留的私人原稿请先放入 `archives/`。应用删除或移动条目后，旧文件不会继续残留在当前备份中。

备份方向是 OpenFic → 文档仓库，日常写作在 OpenFic 中完成。已有 Git 仓库若有未提交修改，脚本会停止，先核对处理已有工作再导出。脚本不初始化仓库、不提交或推送；完成后检查 Git 差异，按授权提交并推送以保存这次快照。新备份目录可自行执行 `git init`。

本机的 `fanpai-dashijie` 和 `just-us-four` 分别备份《反派大师姐想活下去》和《四个人，刚刚好》，均位于 OpenFic 相邻目录。各仓库的 `AGENTS.md` 保存对应的导出命令、归档说明及 GitHub、Gitea 双远端推送规则。

本次导出 ZIP、导出信息和替换前的文件副本保存在 `output/exports/document-backup-时间/`；写入失败时可从其中的 `before/` 恢复被替换的文件。这是当前文档备份，不包含应用历史与会话，也不会重启服务。

## 模型接入

先在「设置 → 提供商」配置连接类型、服务地址与凭据，再在「设置 → 模型」选择连接、任务类型和模型 ID。OpenAI-compatible 的 Chat Completions 与 Responses 使用不同连接类型，应与服务端协议一致；本机兼容连接表单预填 `http://127.0.0.1:10100/v1`，可按实际服务修改。模型 ID 使用服务返回的完整值，保留前缀；上下文长度未知时填 `0`。Embedding 与 rerank 分别创建对应任务类型的模型，再到「设置 → 索引」选择。

推理强度从当前连接返回的模型元数据读取，不按型号猜测。模型列表支持 `reasoning_efforts`、`capabilities.reasoning_effort` 和 `effort.supported_levels`，服务返回的新档位会直接出现在选择器中；Chat Completions 发送 `reasoning_effort`，Responses 发送 `reasoning.effort`。“默认”不发送强度参数；未声明档位或明确不支持时只保留默认选项，并提示原因。连接能力按地址、协议及凭据隔离缓存，五分钟后重新查询；在设置中刷新模型列表也会更新能力。

ocx 等聚合服务与直连 provider 使用同一套发现流程。DeepSeek 的档位取自接口的 `effort` 元数据；MiMo 当前模型列表未声明强度档位，使用服务默认行为。模型 ID 必须与服务返回值一致，不自动替换旧型号或猜测别名。

## 开发检查

依赖安装完成后，在仓库根目录运行：

```powershell
.\scripts\check.ps1
```

默认检查后端格式、lint、类型与测试，以及前端格式、lint、类型、`pnpm run test` 和构建。前端测试依次运行 `test:unit` 与 `test:browser`；浏览器测试使用本机 Chrome 和独立临时服务，不连接正式后端。

快速检查可跳过测试与构建：

```powershell
.\scripts\check.ps1 -SkipTests -SkipBuild
```

后端使用 Python 3.12/3.13、uv 和 Ruff；前端使用 pnpm。

## 来源

本项目基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 持续改造，采用 [Apache License 2.0](./LICENSE)。
