# OpenFic 个人小说协作分支

![OpenFic Banner](./banner.svg)

这是一个基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 长期改造的个人分支，用于在本地管理多本小说，并让 AI 参与设定讨论、提纲整理和正文创作。

该分支主要服务于单人本地使用，不以维持与原项目可直接合并、发布 PyPI 包或维护公开社区为目标。

## 核心目标

- **多项目隔离**：会话、引用、设定、人物、提纲、笔记和待审变更都以 `project_id` 为边界，默认不跨书读取。
- **讨论与创作分离**：讨论会话可以长期保留，但讨论结论不会自动变成正式设定。
- **信息边界**：资料统一标记为公开、仅全局或隐藏。Discuss、Plan 可使用公开资料或全局资料范围，已有会话只允许向全局升级；Build 仅使用公开资料，隐藏资料对所有 Agent 不可见。
- **人工参与写作**：当前受控创作入口支持起草当前场景。AI 结果只有经作者采用才进入正文，生成过程不直接写入正式正文。
- **人工确认写入**：Discuss Agent 的长期资料提议进入待审列表；通用 Agent 的正式资料写入仍由工具逐次请求确认。未审提议不进入正式资料上下文；采用时校验资料基线，冲突时不覆盖。
- **可往返的文档工作流**：支持 OpenFic 项目资料包和声明式 Markdown 源包，覆盖设定与章节正文；应用完整备份另行处理。

## 文档分工

- 本文件说明当前可用能力、产品与数据边界、运行方式和统一验证入口。
- [backend/README.md](./backend/README.md) 只提供后端子包的最小开发入口，不重复产品和部署说明。
- [docs/openfic-import.example.yaml](./docs/openfic-import.example.yaml) 只提供 Markdown 源包映射的机器可读示例；实际格式以解析器和测试为准。

## Windows 本地运行

正式服务直接运行在 Windows，访问 <http://127.0.0.1:18081/>，不依赖 Docker 或前端开发服务器。Python 后端同时提供构建后的网页和 API；健康检查为 <http://127.0.0.1:18081/api/v1/health>。

### 准备环境与构建网页

使用 PowerShell 7、项目支持的 Python 3.12/3.13、uv 和 pnpm。首次安装在仓库根目录执行：

```powershell
cd backend
uv sync --frozen
cd ../frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
```

日常写作不需要重新构建。修改前端代码后运行 `pnpm build`；更新后端代码或依赖后重启服务。正式前端使用当前网页地址访问 API，不要在构建环境中设置指向测试服务的 `VITE_BACKEND_URL`。

### 管理服务

在仓库根目录执行：

```powershell
./scripts/openfic-service.ps1 start
./scripts/openfic-service.ps1 status
./scripts/openfic-service.ps1 logs
./scripts/openfic-service.ps1 restart
./scripts/openfic-service.ps1 stop
```

启动脚本后台运行服务，重复 start 不会启动第二份；端口被其他进程占用时会报错，不会杀掉占用者。stop 使用带令牌的关停接口，并等待服务退出。日志位于 `data/logs`，管理状态位于 `data/runtime/openfic.json`，均不纳入 Git。

本机统一入口 `~/.local/scripts/local-services.ps1` 已接入 OpenFic：运行 `local-services.ps1 start all` 会与其他本地服务一起启动；也可以使用 `local-services.ps1 status openfic` 或 `local-services.ps1 restart openfic` 单独管理。

需要实时预览前端修改时，可单独使用前端 dev 服务。它与正式的静态网页运行方式不同；测试后端应指定独立的数据目录。

## 数据与资料交换

管理脚本默认使用仓库根目录的 `data`（本机为 `E:\GitHub-Repos\OpenFic\data`），不使用 `backend/data` 的测试副本。隔离验证可通过 `-DataPath` 与 `-Port` 指定另一个目录和端口。数据目录不纳入 Git，包含小说正式数据、提供商配置和会话记录。

### 应用完整备份

完整备份由服务端快照和浏览器伴随包组成。先停止编辑，在「设置 → 高级」导出浏览器伴随包，再执行：

```powershell
./scripts/openfic-service.ps1 backup -BrowserBackupPath "$HOME/Downloads/openfic-browser-backup-时间.json"
```

快照默认保存到 `output/backups/`，包含整个数据目录、配置的外置数据、有效加密密钥、源码工作树、已构建网页和文件校验和。脚本暂停受管理服务，完成后恢复运行；校验和用于发现文件缺失或损坏。省略伴随包只能得到服务端备份，不能包含浏览器里的未提交内容。

伴随包覆盖导出所在浏览器档案和网站地址的 IndexedDB 及应用偏好，不包含其他浏览器或不同地址中的工作。恢复后的草稿仍是未提交工作副本，不会自动覆盖正式正文。浏览器导入要求没有现存业务数据；应先在独立浏览器档案中验证。

恢复只接受新目录，不覆盖正式盘：

```powershell
./scripts/openfic-service.ps1 restore -SnapshotPath ./output/backups/快照目录 -RestorePath ./output/restored-openfic
```

恢复目录中的 `source` 保留对应源码，`data` 和 `external` 保留服务数据；按恢复提示准备源码环境并指定 `restore-environment.json` 启动。不要把旧运行状态、PID 或关停令牌用于新服务。备份含凭据和小说内容，应作为私有数据保管。

### 项目资料交换

书架中每个项目提供两类资料包：

- **OpenFic 项目资料包**：保留资料与章节的对象 ID、顺序、可见性、卷和基线信息；不是会话、全局配置、检查点及浏览器草稿的完整应用备份。
- **Markdown 源包**：使用 `openfic-import.yaml` v2 将仓库相对目录映射到背景设定、角色、提纲、笔记和正文。映射根目录中的文件是根级条目，下一层目录表达文件夹或卷；不支持更深层级，也不通过条目标记覆盖目录归属。每个文件可包含一个或多个 `<!-- openfic:item` 元数据块；块内保留稳定 ID、名称、顺序及资料属性，后续正文直到下一个标记或文件末尾，Markdown 标题不参与拆分。导出可按规则选择每条目一文件或每目录合并一文件，不跨目录合并。文件名方便阅读，不决定条目身份；移动文件可以改变归属。文件夹身份、空文件夹和顺序记录在 YAML 中，重命名目录时应同步调整对应路径。

源包导出会转义正文中与保留标记完全相同的独占行，导入时还原；手写标记示例也需遵循转义规则，详见配置示例。旧 v1 标题拆分源包仍可导入，新导出一律使用 v2；旧配置导出时改用默认类型目录，不再回写原有标题组合文件。OpenFic 项目资料包则以首个 H1 表示名称，后续 H1 属于正文，不再限制正文标题级别。

导入始终应先生成预览，冲突或错误未处理前不应应用。通用配置示例见 [docs/openfic-import.example.yaml](./docs/openfic-import.example.yaml)。

正式资料以 SQLite 为准；编辑器与 Dexie 保存未提交工作，React Query 保存可刷新的 API 缓存，LanceDB 是派生检索索引。正文与笔记保存会核对编辑基准；本地稿和正式内容同时变化时保留双方，明确选择采用本地稿或使用已保存版本，不按更新时间自动覆盖。

数据库初始化以 `20260908` 为基线，后续必要的结构变化仍由 Alembic 管理。旧升级链不再随当前版本分发；恢复早期快照应使用该快照对应源码及其中的转换工具，不把旧库直接交给当前版本，也不跳过结构验证修改版本标记。

## 模型接入与备用运行

默认安装保留通用 OpenAI-compatible 接入。本机连接地址建议为 `http://127.0.0.1:10100/v1`，由 OpenCodex 管理上游；OpenFic 不读取代理内部登录凭据。无认证连接可留空密钥。Chat Completions 和 Responses 使用各自的连接类型，模型 ID 保留代理返回的完整前缀；上下文长度未知时填 `0`，不从名称推测能力。

专用 SDK 按需安装，例如在 `backend` 执行 `uv sync --frozen --extra deepseek`。支持的 extras 为 `amazon-nova`、`anthropic`、`cohere`、`deepseek`、`google-genai`、`groq`、`mistral`、`nvidia`、`openrouter`；未安装时保留既有配置并提示缺失适配。Embedding 与 rerank 配置独立于聊天连接。

不使用外部错误遥测，异常保留在本地日志和界面错误提示中。Docker 作为备用入口保留，可用 `docker build -t openfic .` 构建；容器访问宿主地址为 `host.docker.internal`，不能使用容器自身的 `127.0.0.1`。当前本机 OpenCodex 会拒绝容器地址的请求（`origin_rejected`），因此备用容器需另配可访问的兼容服务，或由用户调整代理允许范围。验证实例使用独立数据卷，不与本地正式服务同时挂载同一份数据。

## 开发与验证

在完成依赖安装后，从仓库根目录运行统一检查：

```powershell
.\scripts\check.ps1
```

默认会运行后端格式、lint、类型检查和测试，以及前端格式、lint、类型检查和构建。快速本地检查可跳过较耗时的测试或构建：

```powershell
.\scripts\check.ps1 -SkipTests -SkipBuild
```

后端使用 Python 3.12+ 和 uv：

```powershell
cd backend
uv sync --frozen
uv run pytest
```

前端使用 Node.js 和 pnpm：

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm type-check
pnpm build
```

改动数据模型或导入导出逻辑时，还应在空数据库和正式数据副本上验证，并用隔离数据目录做真实页面回归；本地运行或 Docker 均可。

## 上游更新策略

仓库保留原 OpenFic 远程用于查看和比较，但不再追求与原项目的 `main` 分支保持可直接合并。上游变更按实际价值选择性吸收，主要关注：

- 安全修复和数据修复。
- 依赖、模型提供商和 API 兼容性。
- 能明确减少本分支维护成本的实现。

不机械合并上游社区文档、发布工作流或与当前产品方向冲突的交互改动。

## 许可证与来源

本项目基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 改造，继续使用 [Apache License 2.0](./LICENSE)。
