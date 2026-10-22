# OpenFic Backend

OpenFic 的 FastAPI 后端与 Python 打包入口。项目定位、本地运行方式、数据边界和开发命令见仓库根目录的 [README.md](../README.md)。

首次安装、后端依赖声明／锁文件变化或重建环境时，在本目录执行：

```powershell
uv sync --frozen
```

`deployment` 组包含 `langchain-deepseek>=1.0.1`，默认依赖组为 `dev` 和 `deployment`，普通 `uv sync` 也会保留部署 SDK。添加其他部署 SDK 使用 `uv add --group deployment langchain-anthropic`，移除使用 `uv remove --group deployment langchain-anthropic`，并将 `pyproject.toml` 与 `uv.lock` 一起提交。原有 provider extras 保留。

普通后端源码更新只需检查并重启，不升级依赖。检查使用 `uv run --no-sync ...`，例如：

```powershell
uv run --no-sync pytest
```
