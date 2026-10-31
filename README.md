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
- [独立服务管理接口](docs/service-management.md)：外部程序调用、状态、退出码与互斥约定。
- [docs/openfic-import.example.yaml](./docs/openfic-import.example.yaml)：Markdown 源包映射示例。
- [AGENTS.md](./AGENTS.md)：仓库协作与部署规则。

## 目录分工

| 目录 | 用途与保留规则 |
| --- | --- |
| `data/` | 本机正式服务的数据、配置、日志与运行状态，按私有数据保护。 |
| `backend/` | FastAPI 后端与 Python 打包入口；`backend/data/` 保留现有验证副本，不是本机正式数据盘。 |
| `frontend/` | 网页界面源码与构建配置。 |
| `service/` | 独立 Python 服务管理程序，负责生命周期、备份与恢复的协调；入口为 `python -m service`。 |
| `scripts/` | 文档备份与开发检查脚本。 |
| `docs/` | 少量维护文档与资料交换示例。 |
| `output/` | 需要保留的产物；`backups/` 保存备份，`reports/` 保存审查与验证报告，不按临时文件清理。 |
| `.tmp/` | 仓库临时工作文件，使用 `YYYYMMDD-任务名` 命名；历史遗留的私有原稿须明确保护，清理前逐项确认，不得整目录删除。 |

审查报告、验证日志和截图保存在 `output/reports/`，属于本地历史记录，不纳入 Git。

`.venv/`、`node_modules/` 和 `frontend/dist/` 虽可重建，但分别用于运行、开发和正式网页加载，不作为日常缓存清理。

## 本地运行

正式服务运行在 Windows，地址为 <http://127.0.0.1:18081/>，由后端同时提供构建后的网页与 API，健康检查为 <http://127.0.0.1:18081/api/v1/health>。

使用 Python 3.14、uv 和 pnpm；`backend/.python-version` 固定解释器系列，`backend/uv.lock` 固定依赖。应用与独立服务管理程序共用该环境。以下命令以 PowerShell 为例。首次准备环境并构建网页：

```powershell
cd backend
uv sync --frozen
cd ../frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
```

`uv sync --frozen` 会安装锁文件中的开发与部署依赖。提供商 SDK 的添加和移除方式见 [后端开发说明](backend/README.md)。开发检查使用 `uv run --no-sync ...`，普通源码更新不升级依赖。

在仓库根目录管理服务：

```powershell
uv run --no-sync --project backend python -m service start
uv run --no-sync --project backend python -m service status
uv run --no-sync --project backend python -m service restart
uv run --no-sync --project backend python -m service stop
```

服务数据默认位于仓库根目录的 `data`，端口为 `18081`。日志在 `data/logs`，运行状态在 `data/runtime/openfic.json`。`status` 返回单个 JSON 对象；外部管理器的调用、退出码和互斥规则见 [独立服务管理接口](docs/service-management.md)。运行记录及关闭凭据由 OpenFic 管理，外部界面通过 `python -m service` 调用公开命令。

服务管理程序通过 `OPENFIC_DATA_DIR` 为主服务指定数据目录。未设置该变量时，使用 CLI（`openfic serve`）启动默认使用用户目录下的 `~/.openfic`；绕过 CLI、直接加载后端应用时才回退到 `backend/data/`。`backend/data/` 及现有数据继续保留，独立运行后端时应明确选择数据目录。

日常写作无需重新构建。纯前端代码更新后，在 `frontend/` 执行 `pnpm build`；前端锁文件变化时，先执行 `pnpm install --frozen-lockfile` 再构建。仅修改后端 Python 源码时，完成检查后重启服务即可。正式网页使用当前服务地址访问 API，构建时保持 `VITE_BACKEND_URL` 未设置，以免连接到测试后端。隔离验证可用服务脚本的 `--data-path` 和 `--port` 指定独立数据目录与端口。

首次安装、重建 Python 环境或后端依赖声明／锁文件变化时，在 `backend/` 执行 `uv sync --frozen`，更新后按需重启后端。普通源码更新不升级依赖。

## 数据与模型配置

正式资料保存在服务数据目录；浏览器未保存草稿需要另行导出伴随包。项目资料包用于交换当前资料，不替代完整备份。

- [数据管理与资料交换](docs/data-management.md)：完整备份恢复、文档历史、资料包和文档仓库导出。
- [模型接入与配置](docs/model-configuration.md)：提供商、目录同步、模型能力和连接适配。

## 开发检查

依赖安装完成后，在仓库根目录运行：

```powershell
.\scripts\check.ps1
```

默认检查后端、服务管理程序及 Python 脚本的格式、lint 和类型，并运行后端测试；前端执行格式、lint、类型检查、`pnpm run test` 和构建。前端测试依次运行 `test:unit` 与 `test:browser`；浏览器测试使用本机 Chrome 和独立临时服务，不连接正式后端。

快速检查可跳过测试与构建：

```powershell
.\scripts\check.ps1 -SkipTests -SkipBuild
```

Python 使用 3.14、uv 和 Ruff，命令行类型检查使用 ty；前端使用 pnpm、Oxlint 和 Oxfmt。

### 代码职责与检查范围

前端以功能领域组织代码。TanStack Query 管理服务器快照和请求状态，React Hook Form + Zod 管理复杂表单草稿与验证；编辑器工作副本、撤销历史和持久恢复状态继续由编辑器、Zustand 与 Dexie 按各自职责管理。实时事件更新服务器投影，不应覆盖尚未保存的编辑内容。静态视觉样式归组件 CSS 或 Radix props，共同视觉值归设计变量，运行时计算值可以使用 inline style；具体规则见 [前端设计与维护约束](docs/frontend-design.md)。

普通 HTTP 接口以 FastAPI 的 OpenAPI 契约为源，由 Orval 生成 TypeScript 类型和请求函数。生成代码不手改；请求基础设施负责认证、后端地址与超时，领域适配负责界面数据转换和下载行为，Query hooks 负责缓存与刷新。Socket.IO 和流式输出保留各自的协议、取消与恢复生命周期。

接口声明变更后，在 `frontend/` 执行 `pnpm api:generate`，并将 `openapi.json` 与 `src/api/generated/` 一起提交。`pnpm api:check` 在隔离临时目录重新生成并比较，不修改已保存的契约。两条命令使用本地后端依赖，不启动服务、不读取用户设置或秘密；常规质量检查也包含契约一致性检查。

`lint` 检查代码规则与循环依赖；`format:check` 检查格式而不写文件；`type-check` 分别检查应用、构建与生成配置、现有测试代码，再执行类型感知 lint。测试配置覆盖 `src/**/*.test.ts(x)` 和 `tests/`，单元测试与浏览器测试仍使用原有运行入口。`build` 生成网页与预缓存清单，不启动后端。检查通过不代替实际页面的交互与视觉验收。

后端路由负责 HTTP 边界，领域操作负责业务规则和生命周期，持久化模块负责数据访问。普通请求沿用 session 依赖的提交和回滚；长任务或跨资源操作的阶段提交由对应业务操作明确负责，不假设主数据库、checkpoint 和文件能够跨资源原子提交。启动配置与运行时设置分别管理；密钥文件和加密值保留在原存储位置，普通查询不返回原始秘密。连接编辑时留空密钥表示保留，输入新值表示替换，清除必须显式选择。

## 来源

本项目基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 持续改造，采用 [Apache License 2.0](./LICENSE)。
