# 独立服务管理接口

OpenFic 的生命周期由仓库根目录的独立 Python 程序 `service/` 管理，唯一入口为 `python -m service`，应用备份与外部管理界面共用它。程序使用 Python 3.14 和后端环境中的 `psutil`。管理命令完成后退出，主服务在独立进程中继续运行。

## 调用

首次安装或依赖变化后，在 `backend/` 执行 `uv sync --frozen`。在仓库根目录可直接执行：

```powershell
uv run --no-sync --project backend python -m service status
```

外部程序使用独立进程和参数数组调用，不拼接 shell 字符串。以下 Python 示例直接使用 OpenFic 后端虚拟环境的解释器，避免依赖调用方的 Python 环境：

```python
import json
import os
import subprocess
from pathlib import Path

root = Path("E:/Applications/OpenFic")  # 替换为实际安装目录
python = root / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
result = subprocess.run(
    [str(python), "-m", "service", "status"],
    cwd=root,
    capture_output=True, text=True, encoding="utf-8", timeout=15,
)
status = json.loads(result.stdout)
```

启动、停止和重启将 `status` 替换为 `start`、`stop`、`restart` 并追加 `--json`。机器调用应分别捕获 stdout、stderr，不使用合并输出。`status` 始终输出 JSON，生命周期命令不带 `--json` 时输出供人工阅读的文字。

| 参数 | 含义 |
| --- | --- |
| `--data-path` | 实例数据目录；默认是程序所在仓库的 `data`。外部调用建议传绝对路径。 |
| `--port` | 实例端口，默认 `18081`；每次管理同一实例应传相同端口。 |
| `--restore-environment-path` | 恢复工具生成的 `restore-environment.json`，首次启动恢复副本时指定。 |
| `--json` | `start/stop/restart` 的机器输出模式；`status` 可省略。不适用于备份恢复。 |

调用 `python -m service` 时，工作目录必须是所管理副本的仓库根目录；相对路径参数以该目录解析。管理程序会为主服务设置后端工作目录。外部调用方只使用公开命令和返回结果，不读取或修改内部运行记录、关闭令牌或锁文件。

## 状态与退出码

正常停止示例：

```json
{"schema_version":1,"state":"stopped","detail":"No managed process, listening port or healthy endpoint was found.","pid":null,"port":18081,"data_directory":"E:\\Applications\\OpenFic\\data"}
```

| state | 含义 | status 退出码 |
| --- | --- | --- |
| `running` | 进程身份、端口归属和健康检查均通过；`pid` 是已核实的进程。 | 0 |
| `stopped` | 未发现所管理进程、监听端口或健康端点。 | 0 |
| `warning` | 可确认的异常，例如端口被其他进程占用、身份不符、进程不健康，或管理操作持锁。 | 0 |
| `unknown` | 无法可靠检查，例如权限不足、运行记录损坏或系统查询失败。 | 1 |

`detail` 用于展示，不作为程序分支判断依据。`pid` 仅在确认进程归属后提供，否则为 null。管理锁被持有时额外返回 `busy: true`，表示生命周期操作或备份正在进行；这不等于服务故障或停止。其余状态可省略 `busy`。

`status` 不启动服务，不创建数据目录、状态文件或锁文件。状态是查询时的快照，不是后续操作的授权；每个生命周期命令都会重新校验身份和互斥条件。

生命周期命令的 JSON 增加 `action` 和 `ok`。成功退出 0；失败退出 1，stderr 给出可读原因，JSON 中 `ok` 为 false。启动成功意味着已健康就绪，停止成功意味着已确认停止。重复启动正常实例和重复停止已停止实例都成功。未知参数、解释器或依赖缺失等入口错误可能没有 JSON；调用者必须处理启动失败、非零退出码和无效输出。

返回结果不包含关闭令牌、加密密钥或完整内部状态。日志写入实例的 `logs` 目录。

## 互斥和超时

OpenFic 在同一数据目录的 `runtime/openfic.lock` 上串行执行启动、停止、重启和备份。遇到竞争的生命周期命令直接失败并报告忙碌，不自动排队。外部调用方不应自行持有该锁后调用管理程序，也不应另行创建主服务进程、发关闭请求或清理状态文件。

备份从停服到恢复运行全程持锁。`busy: true` 表示管理操作正在进行，调用方不应因暂时停服触发自动拉起；操作结束后重新查询状态。

启动健康等待上限为 45 秒，单次健康请求最多等待 2 秒；正常关闭请求最多等待 5 秒，随后等待进程退出最多 30 秒，另外还有进程检查和命令启动开销。备份遇到已接受或结果不确定的关闭请求时，恢复逻辑会再等待原进程退出最多 30 秒，不强制结束尚未退出的实例。建议调用超时：status 15 秒、start 90 秒、stop 60 秒、restart 150 秒；备份恢复耗时随数据量增长，不套用生命周期的固定超时。超时表示结果未确认，应先重新查询状态，不据此杀死服务进程或立即重试。若管理命令仍在执行，保留其操作句柄并等待结果。

## 独立备份与恢复

在仓库根目录执行：

```powershell
uv run --no-sync --project backend python -m service backup --browser-backup-path '浏览器伴随包.json'
uv run --no-sync --project backend python -m service restore --snapshot-path '快照目录' --restore-path '新的恢复目录'
```

备份保留原运行状态及实际路径设置：原先运行则正常停服、创建快照，随后按原设置恢复启动；快照失败也尝试恢复运行并返回失败。原先停止则备份后仍保持停止。备份与恢复均可独立执行。浏览器伴随包、快照校验和恢复实例的完整操作见 [数据管理与资料交换](data-management.md#应用完整备份与恢复)。

恢复目标必须是新目录，不覆盖正式实例。之后管理恢复副本时，继续使用同一个数据目录和端口；重启及备份后的重新启动沿用运行记录中已捕获的路径设置。
