# OpenFic 个人小说协作分支

![OpenFic Banner](./banner.svg)

这是一个基于 [syrizelink/OpenFic](https://github.com/syrizelink/OpenFic) 长期改造的个人分支，用于在本地管理多本小说，并让 AI 参与设定讨论、提纲整理和正文创作。

该分支主要服务于单人本地使用，不以维持与原项目可直接合并、发布 PyPI 包或维护公开社区为目标。

## 核心目标

- **多项目隔离**：会话、引用、设定、人物、提纲、笔记和待审变更都以 `project_id` 为边界，默认不跨书读取。
- **讨论与创作分离**：讨论会话可以长期保留，但讨论结论不会自动变成正式设定。
- **信息边界**：局部讨论和写作 Agent 遵守当前项目的写作可见性；全局讨论只在当前项目内放宽该边界。
- **人工参与写作**：AI 可以起草、续写、改写或润色，但正文和长期资料最终由作者确认。
- **待审变更**：AI 对背景、人物、提纲和笔记的长期修改先进入待审列表，经采用后才写入正式资料。
- **可往返的文档工作流**：支持 OpenFic 原生备份包和声明式 Markdown 源包，避免脚本直接解析或改写数据库。

当前进度、已实现边界和后续阶段见 [ROADMAP.md](./ROADMAP.md)。

## 本地运行

当前主要使用 Docker 运行。

### 构建镜像

```powershell
docker build -t openfic:local .
```

### 新建容器

```powershell
docker run -d --name openfic --restart unless-stopped -p 127.0.0.1:8000:8000 -v openfic-data:/data openfic:local
```

打开 <http://127.0.0.1:8000/>，健康检查为 <http://127.0.0.1:8000/api/v1/health>。

> [!IMPORTANT]
> 重建现有容器前，先用 `docker inspect openfic` 确认当前挂载的数据卷。不要为了复制示例命令而替换正在使用的 `/data` 数据卷。

## 数据与资料交换

OpenFic 运行数据保存在容器的 `/data` 目录，通过 Docker 数据卷持久化。代码仓库不包含小说正式数据、提供商密钥或会话记录。

书架中每个项目提供两类资料包：

- **OpenFic 项目资料包**：面向完整备份和恢复，保留对象 ID、顺序、可见性和基线信息。
- **Markdown 源包**：面向人类可读的文档仓库，根据 `openfic-import.yaml` 在背景设定、角色、提纲和笔记之间做语义级映射。

导入始终应先生成预览，冲突或错误未处理前不应应用。通用配置示例见 [docs/openfic-import.example.yaml](./docs/openfic-import.example.yaml)。

## 开发与验证

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
