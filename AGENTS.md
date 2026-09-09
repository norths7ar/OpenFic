# 仓库规则

- 作者已确定本仓库为永久分支开发，对upstream仓库只参考、选择性采用功能性的更新，不再考虑merge / PR
- OpenFic **数据盘**与 fanpai-dashijie 互为数据备份。同一时刻只能修改一侧，另一侧必须只读。导入、导出或跨仓库写入前，必须检查两侧变化并明确同步方向。两侧都发生变化时必须停止，禁止自行合并或覆盖。
- 及时清理 Docker 中已确认不再需要的旧版镜像和容器。
- 本机正式服务使用 Windows 本地运行（127.0.0.1:18081），由 `scripts/openfic-service.ps1` 管理，正式数据位于仓库根目录 `data`；`backend/data` 下的验证副本不是正式数据。
- Git 远端：`origin` 是 GitHub 上的 OpenFic 主远端，`gitea` 是 Gitea 备份远端，`upstream` 仅供参考。用户要求推送时，将本次指定的分支或标签同步推送到 `origin` 和 `gitea`，分别核验结果；任一失败须明确报告，不向 `upstream` 推送。仅要求提交时，不自动推送。

## 版本发布

- 使用 `vX.Y.Z` 附注标签；发布前统一 `frontend/package.json`、`backend/pyproject.toml` 及相关锁文件中的版本，并验证实际运行版本。
- 维护 `CHANGELOG.md`：在 `Unreleased` 中归纳已完成、尚未发布的用户可感知变化，不逐条复制提交，也不记录计划或未完成事项。
- 小目标分别实施、提交和验收，不要求每个修复或小目标升版本、打标签或创建 Release；积累一批稳定成果后再确定版本号，将 `Unreleased` 整理为带版本号和日期的更新记录。
- 分支和标签按上述远端规则同步；以 CHANGELOG 记录更新、附注标签标记稳定版本，不创建 GitHub Release，不制作安装包。
- 正式数据、凭据、缓存及备份不进入 Git。
