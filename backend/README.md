# OpenFic Backend

OpenFic 的 FastAPI 后端与 Python 打包入口。项目定位、本地运行方式、数据边界和开发命令见仓库根目录的 [README.md](../README.md)。

常用验证：

```powershell
../scripts/sync-dependencies.ps1
uv run --no-sync pytest
```

添加原生 provider 时使用 `../scripts/sync-dependencies.ps1 -Extra deepseek`；后续同步会记住选择，具体规则见根目录 README 的「本地运行」。
