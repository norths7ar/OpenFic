# OpenFic 个人小说协作分支

![OpenFic Banner](./banner.svg)

这是一个基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 长期改造的个人分支，用于在本地管理多本小说，并让 AI 参与设定讨论、提纲整理和正文创作。

该分支主要服务于单人本地使用，不以维持与原项目可直接合并、发布 PyPI 包或维护公开社区为目标。

## 核心目标

- **多项目隔离**：会话、引用、设定、人物、提纲、笔记和待审变更都以 `project_id` 为边界，默认不跨书读取。
- **讨论与创作分离**：讨论会话可以长期保留，但讨论结论不会自动变成正式设定。
- **信息边界**：资料统一标记为公开、仅全局或隐藏。Discuss、Plan 可使用公开资料或全局资料范围，已有会话只允许向全局升级；Build 仅使用公开资料，隐藏资料对所有 Agent 不可见。
- **人工参与写作**：当前受控创作入口支持起草当前场景；续写、按节拍改写、选区润色和连续性检查仍在路线图中。AI 结果只有经作者采用才进入正文。
- **人工确认写入**：Discuss Agent 的长期资料提议进入待审列表；通用 Agent 的正式资料写入仍由工具逐次请求确认，后续是否收敛为单一机制见路线图。
- **可往返的文档工作流**：支持 OpenFic 原生备份包和声明式 Markdown 源包，避免脚本直接解析或改写数据库。

当前进度、已实现边界和后续阶段见 [ROADMAP.md](./ROADMAP.md)。

## 文档分工

- 本文件只说明当前可用能力、运行方式、数据边界和统一验证入口。
- [ROADMAP.md](./ROADMAP.md) 是产品边界、阶段状态、架构候选和待决策事项的唯一权威；未勾选事项不是已经承诺的实现计划。
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

管理脚本将 `OPENFIC_DATA_DIR` 固定为仓库根目录的 `data`（本机为 `E:\GitHub-Repos\OpenFic\data`），不使用 `backend/data` 的测试副本。数据目录不纳入 Git，包含小说正式数据、提供商配置和会话记录。

备份应覆盖整个数据目录：`openfic.db`、`checkpoints.db`、`.key`、附件、图片及索引等。数据库运行时可能存在 WAL 文件，完整文件备份应先停止服务，复制完毕后再启动；`.key` 用于解密已保存的提供商密钥，不应重新生成或遗漏。代码更新与数据备份是两件事。

书架中每个项目提供两类资料包：

- **OpenFic 项目资料包**：面向完整备份和恢复，保留对象 ID、顺序、可见性和基线信息。
- **Markdown 源包**：面向人类可读的文档仓库，根据 `openfic-import.yaml` 在背景设定、角色、提纲和笔记之间做语义级映射。

导入始终应先生成预览，冲突或错误未处理前不应应用。通用配置示例见 [docs/openfic-import.example.yaml](./docs/openfic-import.example.yaml)。

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

改动数据模型或导入导出逻辑时，还应在空数据库上验证 Alembic 迁移，并用隔离的 Docker 数据卷做真实页面回归。

## 上游更新策略

仓库保留原 OpenFic 远程用于查看和比较，但不再追求与原项目的 `main` 分支保持可直接合并。上游变更按实际价值选择性吸收，主要关注：

- 安全修复和数据修复。
- 依赖、模型提供商和 API 兼容性。
- 能明确减少本分支维护成本的实现。

不机械合并上游社区文档、发布工作流或与当前产品方向冲突的交互改动。

## 许可证与来源

本项目基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 改造，继续使用 [Apache License 2.0](./LICENSE)。
