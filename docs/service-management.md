# 独立服务管理接口

OpenFic 的生命周期由 `scripts/openfic-service.ps1` 实现，应用备份与外部管理界面共用它。需要 PowerShell 7.4 或更新版本，不依赖 Service Desk（SD）的源码、安装目录或运行状态，也不启动额外的管理服务。

## 调用

使用独立进程和参数数组调用，不拼接 shell 字符串。以下 Python 示例只使用标准库：

```python
import json
import subprocess
from pathlib import Path

root = Path("E:/Applications/OpenFic")  # 替换为实际安装目录
result = subprocess.run(
    ["pwsh.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
     str(root / "scripts/openfic-service.ps1"), "status"],
    capture_output=True, text=True, encoding="utf-8", timeout=15,
)
status = json.loads(result.stdout)
```

启动、停止和重启将 `status` 替换为 `start`、`stop`、`restart` 并追加 `-Json`。机器调用应分别捕获 stdout、stderr，不使用合并输出。`status` 始终输出 JSON，生命周期命令不带 `-Json` 时输出供人工阅读的文字。

| 参数 | 含义 |
| --- | --- |
| `-DataPath` | 实例数据目录；默认是脚本所在仓库的 `data`。外部调用建议传绝对路径。 |
| `-Port` | 实例端口，默认 `18081`；每次管理同一实例应传相同端口。 |
| `-RestoreEnvironmentPath` | 恢复工具生成的 `restore-environment.json`，首次启动恢复副本时指定。 |
| `-Json` | `start/stop/restart` 的机器输出模式；`status` 可省略。不适用于备份恢复。 |

进程工作目录由脚本设置，不依赖调用者的工作目录。相对路径参数按调用者工作目录解析。SD 只需配置脚本路径及实例参数，不应读取或修改内部运行记录、关闭令牌或锁文件。

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

生命周期命令的 JSON 增加 `action` 和 `ok`。成功退出 0；失败退出 1，stderr 给出可读原因，JSON 中 `ok` 为 false。启动成功意味着已健康就绪，停止成功意味着已确认停止。重复启动正常实例和重复停止已停止实例都成功。未知参数、PowerShell 版本不满足等发生在脚本执行前的错误可能只有 stderr，没有 JSON；调用者必须处理非零退出码和无效输出。

不返回关闭令牌、加密密钥或完整内部状态。`logs` 入口已移除，日志仍写入实例的 `logs` 目录。

## 互斥和超时

OpenFic 在同一数据目录的 `runtime/openfic.lock` 上串行执行启动、停止、重启和备份。遇到竞争的生命周期命令直接失败并报告忙碌，不自动排队。SD 不应自行持有该锁后调用脚本，也不应另行创建进程、发关闭请求或清理状态文件。

备份从停服到恢复运行全程持锁。SD 收到 `busy: true` 时展示操作中，不因暂时停服触发自动拉起；操作结束后重新查询状态。

独立启动引导最多等待 15 秒，随后启动健康等待上限为 45 秒，正常关闭请求最多等待 5 秒，随后等待进程退出最多 30 秒，另外还有进程检查和命令启动开销。建议调用超时：status 15 秒、start 90 秒、stop 60 秒、restart 150 秒；备份恢复耗时随数据量增长，不套用生命周期的固定超时。超时表示结果未确认，应先重新查询状态，不据此杀死服务进程或立即重试。若管理命令仍在执行，保留其操作句柄并等待结果。

## 独立备份与恢复

在仓库根目录执行：

```powershell
./scripts/openfic-service.ps1 backup -BrowserBackupPath '浏览器伴随包.json'
./scripts/openfic-service.ps1 restore -SnapshotPath '快照目录' -RestorePath '新的恢复目录'
```

备份保留原运行状态及实际路径设置：原先运行则正常停服、创建快照，随后按原设置恢复启动；快照失败也尝试恢复运行并返回失败。原先停止则备份后仍保持停止。备份与恢复均不依赖 SD。浏览器伴随包、校验与恢复操作详见 README 的应用完整备份章节。

恢复创建新目录，不覆盖正式实例。在恢复源码中重建依赖后，通过副本自己的脚本启动：

```powershell
uv sync --frozen --project '<恢复目录>/source/backend'
& '<恢复目录>/source/scripts/openfic-service.ps1' start -DataPath '<恢复目录>/data' -RestoreEnvironmentPath '<恢复目录>/restore-environment.json' -Port 18082 -Json
```

之后管理副本时继续传同一个数据目录和端口。重启及备份后的重新启动使用运行记录中已捕获的路径设置。

## SD 切换

先在 SD 中将 OpenFic 操作改为上述命令调用，核对正常启动、重复启动、停止、重启、异常状态、忙碌状态和恢复参数。确认通过后移除 SD 内部的 OpenFic 专用生命周期分支，其他服务不受影响。原有运行记录格式和锁语义保持不变，但属于 OpenFic 内部实现，不再作为 SD 的接口。OpenFic 不负责修改 SD。

## 本次交付验证（2026-10-29）

使用全新隔离数据、独立端口和参数数组调用，未启动或修改正式实例，未调用模型生成接口。

- 状态查询：不存在的数据目录保持不存在；停止状态退出 0；损坏的状态文件返回 unknown／非零，未泄露令牌。
- 生命周期：启动健康后返回，重复启动 PID 不变，重启生成新进程，正常停止与重复停止均成功；捕获 stdout/stderr 的调用能够结束，不被后台进程继承管道阻塞。
- 异常与互斥：其他进程占用端口时返回 warning 并拒绝启动／停止；持锁时报告 busy，竞争启动失败。
- 备份：运行中成功备份后恢复运行；故意使用已有快照目录使备份失败后，仍恢复原实例；停止时备份完成后保持停止。
- 独立恢复：从快照恢复新目录，以 Python 3.12 执行 `uv sync --frozen` 重建虚拟环境，使用副本自己的脚本、数据、恢复环境和端口完成启动／重启／关闭；运行记录的全部数据路径位于恢复目录内。
- 现有备份测试 4 项通过，未新增或修改测试文件。独立代码审查检查了原脚本与新实现的保留关系。

SD 侧适配尚未修改，需在其项目内完成接入验收。关闭超时后的恢复分支已做独立代码审查，未在真实服务中人为制造长时间关闭挂起；超过恢复等待期限会明确报错，不强制终止进程。
