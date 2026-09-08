# 仓库规则

- 作者已确定本仓库为永久分支开发，对upstream仓库只参考、选择性采用功能性的更新，不再考虑merge / PR
- OpenFic **数据盘**与 fanpai-dashijie 互为数据备份。同一时刻只能修改一侧，另一侧必须只读。导入、导出或跨仓库写入前，必须检查两侧变化并明确同步方向。两侧都发生变化时必须停止，禁止自行合并或覆盖。
- 及时清理 Docker 中已确认不再需要的旧版镜像和容器。
- 本机正式服务使用 Windows 本地运行（127.0.0.1:18081），由 `scripts/openfic-service.ps1` 管理，正式数据位于仓库根目录 `data`；`backend/data` 下的验证副本不是正式数据。
- Git 远端：`origin` 是 GitHub 上的 OpenFic 主远端，`gitea` 是 Gitea 备份远端，`upstream` 仅供参考。用户要求推送时，将本次指定的分支或标签同步推送到 `origin` 和 `gitea`，分别核验结果；任一失败须明确报告，不向 `upstream` 推送。仅要求提交时，不自动推送。
