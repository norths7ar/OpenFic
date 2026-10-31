# 数据管理与资料交换

以下管理命令均在仓库根目录执行。安装与启动见 [README](../README.md)，自动化调用约定见 [服务管理接口](service-management.md)。

`data` 保存正式资料、提供商配置、会话记录和文档历史。正式资料以 SQLite 为准；浏览器草稿是未提交工作副本，API 缓存可刷新，LanceDB 是派生检索索引。正文与笔记保存会核对编辑基准，本地稿与正式内容都发生变化时，由作者比较并选择保留的版本。

## 应用完整备份与恢复

完整备份由服务端快照和浏览器伴随包组成。先停止编辑，在「设置 → 高级」导出浏览器伴随包，再执行：

```powershell
uv run --no-sync --project backend python -m service backup --browser-backup-path "$HOME/Downloads/openfic-browser-backup-时间.json"
```

快照默认写入 `output/backups/`，包含数据目录、配置的外置数据、有效加密密钥、源码工作树、已有的网页构建产物和文件校验和。脚本会暂停受管理服务，备份结束后恢复原有运行状态。省略 `--browser-backup-path` 只能得到服务端备份，不能保存浏览器里的未提交工作；快照含小说内容与凭据，应作为私有数据保管。

伴随包保存导出所在浏览器档案和网站地址下的草稿、编辑状态及应用偏好，不包含其他浏览器档案或地址中的工作。

恢复会校验文件清单与校验和，目标必须是新目录：

```powershell
uv run --no-sync --project backend python -m service restore --snapshot-path ./output/backups/快照目录 --restore-path ./output/restored-openfic
```

恢复后的 `source/` 保存对应源码，`data/` 和 `external/` 保存服务数据。从原仓库根目录进入恢复源码的 `source/`，按锁文件重建依赖，再使用 `restore-environment.json` 启动独立实例：

```powershell
cd ./output/restored-openfic/source
uv sync --frozen --project backend
uv run --no-sync --project backend python -m service start --data-path ../data --restore-environment-path ../restore-environment.json --port 18082
```

用新浏览器档案打开恢复实例，在「设置 → 高级」导入快照中的 `browser.json` 并重新加载。导入要求该档案在此地址下没有现存项目、编辑状态或草稿；恢复的草稿仍需作者保存，不会自动覆盖正式正文。

## 文档历史与回收站

章节、背景设定、角色、提纲和笔记均支持文档历史。编辑器工具栏的「历史版本」可预览并恢复标题和正文，不改变当前文件夹或可见性。手工编辑按 5 分钟合并恢复点，每篇保留最近 100 个；导入覆盖、采用待审变更和恢复操作会在内容变化前单独留点。历史从功能启用后的修改开始记录。

删除条目后，可在标签栏右侧的「回收站」预览、恢复或永久删除。回收站不自动清空；恢复沿用原条目 ID，原文件夹或卷不存在时放回对应类型的根目录，ID 占用或角色、背景设定重名时会提示冲突。历史与回收站保存在数据库中，随完整备份保存，不包含在两类资料包中；永久删除回收站条目会清理其对应历史，删除项目会清理整个项目的记录。

## 项目资料交换

书架可导入和导出两类资料包，用于交换当前资料，不替代完整备份：

- **OpenFic 项目资料包**：保留资料、章节的对象 ID、顺序、可见性、文件夹、卷和基线信息，也导出讨论中的用户与助手文字。导入的讨论作为归档，不恢复可继续运行的 Agent 会话；全局配置、运行检查点和浏览器草稿仍需完整备份。
- **Markdown 源包**：在 ZIP 根目录使用 `openfic-import.yaml` v2 映射背景设定、角色、提纲、笔记和正文。映射根目录下的文件是根级条目，下一层目录表示文件夹或卷，支持单层目录归属。

Markdown 源包用 `<!-- openfic:item` 元数据块区分条目并保留稳定 ID，正文中的 Markdown 标题不参与拆分。文件名不决定身份，移动文件可以改变归属；重命名目录时同步修改 YAML 中的 `folders.source`，以保留文件夹身份。导出可选择每条目一文件或每目录合并一文件，具体配置及保留标记的转义方式见 [映射示例](openfic-import.example.yaml)。

导入前先生成预览，核对新增、更新与冲突后再应用。

## 导出到文档备份仓库

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
