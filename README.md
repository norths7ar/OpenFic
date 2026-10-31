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
./scripts/openfic-service.ps1 restart
./scripts/openfic-service.ps1 stop
```

服务数据默认位于仓库根目录的 `data`，端口为 `18081`。日志在 `data/logs`，运行状态在 `data/runtime/openfic.json`。`status` 返回单个 JSON 对象；外部管理器的调用、退出码和互斥规则见 [独立服务管理接口](docs/service-management.md)。运行记录及关闭凭据由 OpenFic 管理，外部界面只调用脚本。

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

保持 OpenFic 服务运行，在仓库根目录用 PowerShell 7 执行。不带参数备份配置中的全部书籍，也可以按完整书名选一本：

```powershell
# 备份配置中的全部书籍
./scripts/export-document-backup.ps1

# 只备份一本
./scripts/export-document-backup.ps1 -Book '示例书名'
```

书名、项目 ID 和目标目录统一保存在本地配置 `scripts/document-backups.json`（已加入 `.gitignore`，不提交到仓库），相对目录以配置文件所在目录为准，与启动命令时的工作目录无关。可用 `-ConfigPath` 选择其他配置；临时导出仍支持 `-ProjectId '项目 ID' -Destination '../小说备份目录'`，显式 `-Destination` 的相对路径以当前工作目录为准。

目标目录须已存在。脚本调用本机正式服务的 Markdown 源包 API，完整下载并解压后更新目标目录；可用 `-BaseUrl` 指定其他服务。根目录的 `.git`、`.gitignore`、`.gitattributes`、`archives`、`README` 和 `AGENTS`（包括带扩展名的名称，不区分大小写）保留，其余内容替换为本次导出。需要长期保留的私人原稿请先放入 `archives/`。应用删除或移动条目后，旧文件不会继续残留在当前备份中。

备份方向是 OpenFic → 文档仓库，日常写作在 OpenFic 中完成。脚本先检查所有选中目标的目录和 Git 状态；任一仓库有未提交修改，就在导出前停止并指出目录。每本书完成后汇总新增、修改和删除的文件数量，没有变化时不替换目标文件。批量备份不是跨仓库事务：若后一本下载或写入失败，已完成的前一本保留。脚本不初始化仓库、不提交或推送；完成后检查 Git 差异，按授权提交并推送以保存这次快照。新备份目录可自行执行 `git init`。

首次使用时创建 `scripts/document-backups.json`，按以下结构填写实际信息；数组中可配置多本书：

```json
[
  {
    "name": "示例书名",
    "project_id": "项目 ID",
    "destination": "../../document-backup"
  }
]
```

本次导出 ZIP 保存在 `output/exports/document-backup-时间-标识/`；有变化时还保存导出信息和替换前副本，写入失败时可从其中的 `before/` 恢复被替换的文件。这是当前文档备份，不包含应用历史与会话，也不会重启服务。

## 模型接入

在「设置 → 提供商」配置连接、同步目录并启用需要的模型；手动添加 ID、停用和删除也在具体提供商中操作。「设置 → 模型」汇总已启用模型，用于设置默认／轻量模型、调用参数和默认速度。OpenAI-compatible 的 Chat Completions 与 Responses 使用不同连接类型，应与服务端协议一致；本机兼容连接表单预填 `http://127.0.0.1:10100/v1`，可按实际服务修改。模型 ID 使用服务返回的完整值，保留前缀；上下文长度未知时填 `0`。Embedding 与 rerank 在提供商中选择对应任务类型，再到「设置 → 索引」配置。

推理强度从当前连接返回的模型元数据读取，不按型号猜测。模型列表支持 `reasoning_efforts`、`capabilities.reasoning_effort` 和 `effort.supported_levels`，服务返回的新档位会直接出现在选择器中；Chat Completions 发送 `reasoning_effort`，Responses 发送 `reasoning.effort`。“默认”不发送强度参数；未声明档位或明确不支持时只保留默认选项，并提示原因。模型目录与能力共用按地址、协议及凭据隔离的五分钟缓存；在设置中手动刷新会立即重新查询。

打开模型相关页面、返回窗口或网络恢复时自动同步，页面可见期间每五分钟检查。新模型进入候选列表，默认不启用；仍在目录中的模型保留本地参数与启用状态。只有完整真实目录成功返回，才清理不再列出的语言模型配置，包括停用和手动添加的条目，并解除默认／轻量模型及 Agent 引用。网络、认证、格式或分页失败不会触发清理。普通读取和生成前能力查询不删除配置；同步使用显式接口，结果汇总展示受影响模型与用途。

默认模型可设为“每次选择”，轻量模型可设为“跟随默认模型”。模型被停用或清理后，对应设置恢复上述状态；没有可用默认模型时，后台任务提示配置，不任意选择其他模型。会话中已选模型消失后，需要重新选择才能继续发送。历史消息与运行记录保留，正在运行的请求不在中途切换模型。嵌入模型绑定的检索索引仍采用专门的保护与重建流程。

OCX 连接在提供商表单中显式选择 OCX 展示适配，其他连接默认使用通用模式，不根据名字或地址推断。仅当同一目录同时包含 `A` 和精确的 `A--fast` 时，合并显示为模型 A，使用独立的 `Standard / Fast` 速度选择。两者分别请求原始 ID `A` 和 `A--fast`，不转换为 `service_tier`。普通 `-fast` 与未配对的 `--fast` 保持独立条目。模型配置保存默认速度，会话可独立覆盖，恢复旧会话不会改写新会话的默认速度。速度与推理强度独立保存；速度退出目录或所选推理档位不受目标速度支持时，提示调整，不静默换速或降档。

原本独立的 `A--fast` 后来形成配对时，同步保留本地记录、名称、参数和启用状态，将其纳入 A 的共享配置；旧会话仍按原始 ID 使用 Fast。切换到 OCX 适配前，若同一配对已保存两条配置，需要先在提供商中保留其中一条，不自动丢弃或合并调用参数。

首次启用自动清理前应备份正式数据。新增配置字段由 Alembic 迁移；已配置连接默认仍为通用模式，需要显式将 OCX 连接切换为 OCX。

API 未声明能力时，使用本地维护的 [reasoning_defaults.toml](backend/app/models/clients/reasoning_defaults.toml) 补充文档默认值、可选值和请求映射。配置按连接类型、完整服务地址和模型 ID 匹配；API 明确声明的档位或不支持状态优先，避免覆盖聚合服务自身的行为。修改配置后重启后端，不需要同步依赖。维护时同时核对 `source` 文档并更新 `checked_on`。

MiMo 当前模型列表没有能力字段，配置依据官方文档提供“默认（开启思考）／开启思考／关闭思考”。Chat Completions 显式选择时发送 `thinking.type`；Responses 将开启映射为 `reasoning.effort=high`、关闭映射为 `none`，其中 `high` 只是开启的协议值，不表示更强的推理。选择默认时仍不发送覆盖参数。

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

### 代码职责与检查范围

前端以功能领域组织代码。TanStack Query 管理服务器快照和请求状态，React Hook Form + Zod 管理复杂表单草稿与验证；编辑器工作副本、撤销历史和持久恢复状态继续由编辑器、Zustand 与 Dexie 按各自职责管理。实时事件更新服务器投影，不应覆盖尚未保存的编辑内容。静态视觉样式归组件 CSS 或 Radix props，共同视觉值归设计变量，运行时计算值可以使用 inline style；具体规则见 [前端设计与维护约束](docs/frontend-design.md)。

普通 HTTP 接口以 FastAPI 的 OpenAPI 契约为源，由 Orval 生成 TypeScript 类型和请求函数。生成代码不手改；请求基础设施负责认证、后端地址与超时，领域适配负责界面数据转换和下载行为，Query hooks 负责缓存与刷新。Socket.IO 和流式输出保留各自的协议、取消与恢复生命周期。

接口声明变更后，在 `frontend/` 执行 `pnpm api:generate`，并将 `openapi.json` 与 `src/api/generated/` 一起提交。`pnpm api:check` 在隔离临时目录重新生成并比较，不修改已保存的契约。两条命令使用本地后端依赖，不启动服务、不读取用户设置或秘密；常规质量检查也包含契约一致性检查。

`lint` 检查代码规则与循环依赖；`format:check` 检查格式而不写文件；`type-check` 分别检查应用、构建与生成配置、现有测试代码，再执行类型感知 lint。测试配置覆盖 `src/**/*.test.ts(x)` 和 `tests/`，单元测试与浏览器测试仍使用原有运行入口。`build` 生成网页与预缓存清单，不启动后端。检查通过不代替实际页面的交互与视觉验收。

后端路由负责 HTTP 边界，领域操作负责业务规则和生命周期，持久化模块负责数据访问。普通请求沿用 session 依赖的提交和回滚；长任务或跨资源操作的阶段提交由对应业务操作明确负责，不假设主数据库、checkpoint 和文件能够跨资源原子提交。启动配置与运行时设置分别管理；密钥文件和加密值保留在原存储位置，普通查询不返回原始秘密。连接编辑时留空密钥表示保留，输入新值表示替换，清除必须显式选择。

## 来源

本项目基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 持续改造，采用 [Apache License 2.0](./LICENSE)。
