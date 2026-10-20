# OPPO 健康国内版云端 MCP 认证手册

本文记录在 Android 15 root 模拟器上使用国内版 OPPO 健康（包名 `com.heytap.health`）登录并配置本地 MCP 的成功流程。操作对象应为自己的账号和健康数据。

## 流程概览

```text
国内版 OPPO 健康登录并开启健康云服务
  -> 从应用私有账号文件读取 accessToken 和 deviceId
  -> 用 MCP 的签名请求读取当天步数响应中的 userTagId / virtual-ssoid
  -> 写入本地 auth.json
  -> 通过 cloud_status 和只读云端接口验证
```

最终认证不依赖 HTTPS 中间人抓包、用户 CA 证书或 Frida。此前的抓包/证书绕过尝试没有用于取值。

## 环境准备

- Android 15 模拟器，设备序列号示例为 `emulator-5554`，已具备 root 权限。
- 安装国内版 OPPO 健康，包名为 `com.heytap.health`。在模拟器界面由账号本人完成登录，并在应用内开启健康云服务。
- Windows PowerShell、Python 3、Android `adb` 和 `curl` 可用。
- 本地 MCP 仓库：`mcp/oppo-health-cloud-mcp`。

确认模拟器、应用和 root：

```powershell
adb devices -l
adb -s emulator-5554 shell pm path com.heytap.health
adb -s emulator-5554 shell su -c id
```

root 检查应显示 `uid=0`。如果 `su` 弹出授权提示，在模拟器中允许本次本地操作。

## 处理登录页“无网络连接”

这次成功登录时，模拟器走直连网络：关闭 Reqable/mitmproxy 等代理，将 Android 全局 HTTP 代理恢复为 `null`，并恢复系统原有证书环境后重开应用。登录和开启健康云服务不需要启用 TLS 解密或 Frida。

可检查代理状态：

```powershell
adb -s emulator-5554 shell settings get global http_proxy
```

若仍有代理地址，先在模拟器网络设置中关闭代理，再重开 OPPO 健康。登录页恢复正常后，由账号本人完成登录和云服务开关。

## 生成 auth.json

认证源文件位于应用私有目录：

```text
/data/user/0/com.heytap.health/files/open_sdk_AC_ACCOUNT_AUTH_FILE_NAME.properties
```

在 PowerShell 中进入 MCP 仓库目录，然后运行下面的脚本。它通过 `adb` 在内存中读取私有文件，使用 MCP 自带的签名请求查找 `userTagId`、`virtual-ssoid` 或 `ssoid`，最后只把三项认证字段写到当前目录的 `auth.json`，不会将字段值打印到终端。

```powershell
Set-Location D:\code\oppo-health\mcp\oppo-health-cloud-mcp
@'
import datetime
import json
import subprocess
from pathlib import Path

from cloud_mcp import _post

serial = "emulator-5554"
source = "/data/user/0/com.heytap.health/files/open_sdk_AC_ACCOUNT_AUTH_FILE_NAME.properties"
result = subprocess.run(
    ["adb", "-s", serial, "exec-out", "su", "-c", f"cat {source}"],
    check=True,
    capture_output=True,
)
text = result.stdout.decode("utf-8-sig")
properties = {}
for line in text.splitlines():
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key in {"accessToken", "deviceId"}:
        properties[key] = value.lstrip()

token = properties.get("accessToken", "")
device_id = properties.get("deviceId", "")
if not token or not device_id:
    raise RuntimeError("账号文件中缺少 accessToken 或 deviceId；请先确认应用已登录")

# deviceId 在该 properties 文件中有双层 JSON 转义。
for _ in range(2):
    try:
        decoded = json.loads(device_id)
    except (TypeError, ValueError):
        break
    if not isinstance(decoded, str):
        break
    device_id = decoded

# 保留 accessToken 原文，包括可能存在的 _shouming 后缀。
auth_for_request = {"token": token, "token_auth_id": device_id}
today = datetime.datetime.now().astimezone().replace(
    hour=0, minute=0, second=0, microsecond=0
)
start = int(today.timestamp() * 1000)
response = _post(
    "v5/c2s/sport/steps/pullStepsDetailData",
    {"startTimestamp": start, "endTimestamp": start + 86_399_999},
    auth_for_request,
)
if response.get("errorCode") != 0:
    raise RuntimeError(f"步数接口失败，errorCode={response.get('errorCode')}")

def find_ssoid(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if normalized in {"usertagid", "virtualssoid", "ssoid"} and child not in (None, ""):
                return str(child)
        for child in value.values():
            found = find_ssoid(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_ssoid(child)
            if found:
                return found
    return None

ssoid = find_ssoid(response)
if not ssoid:
    raise RuntimeError("步数响应中没有找到 userTagId / virtual-ssoid / ssoid")

auth = {"token": token, "token_auth_id": device_id, "ssoid": ssoid}
Path("auth.json").write_text(
    json.dumps(auth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("auth.json 已写入；token、token_auth_id、ssoid 均未输出。步数接口 errorCode=0。")
'@ | python -
```

字段对应关系：

| MCP 字段 | 来源 | 注意事项 |
|---|---|---|
| `token` | `accessToken` | 必须保留完整原文。截掉 `_shouming` 后缀会导致云端返回 `10101`。 |
| `token_auth_id` | `deviceId` | 对文件中的双层 JSON 转义解码后写入。 |
| `ssoid` | 步数响应中的 `userTagId`、`virtual-ssoid` 或 `ssoid` | 脚本通过 MCP 已有签名请求递归查找。 |

`auth.json` 已在 `.gitignore` 中忽略。不要提交认证文件、原始 properties 文件、HAR、代理日志或带响应正文的调试输出。

## 启动与验证

在 MCP 仓库目录中检查认证文件状态：

```powershell
python -c "import cloud_mcp; print(cloud_mcp.cloud_status())"
```

`auth_ready` 为 `true` 表示本地认证文件存在。实际云端验证还需调用只读接口；本次通过步数和体重只读接口的 `errorCode=0` 验证成功。MCP 提供 `cloud_sync`、`cloud_query`、`cloud_analyze` 和 `cloud_status`。`cloud_sync` 会把数据写入本地 SQLite 缓存，并返回样例数据；健康数据属于敏感信息，避免将 MCP 原始结果或屏幕截图贴到公开位置。

stdio MCP 启动命令：

```powershell
python cloud_mcp.py
```

在 MCP 客户端配置中，将命令指向本机 Python，并把 `cloud_mcp.py` 的绝对路径作为参数；工作目录设为仓库目录。若 Python 环境缺少 MCP SDK，可安装 `mcp[cli]`。

## 常见问题

| 现象 | 处理 |
|---|---|
| OPPO 健康登录页提示无网络 | 检查 Android 全局代理，关闭 Reqable/mitmproxy，恢复原有系统证书并重开应用，使用直连网络登录。 |
| `10101` | 重新从账号文件读取完整 `accessToken`；不要删除其后缀。 |
| `10103` | 这是网关/TLS 请求指纹拒绝。MCP 的 `_post` 已使用 `curl` 和对应 User-Agent；不要用 `urllib` 替换该请求路径。 |
| `10100` | 检查请求头或签名输入是否被自行增删。使用仓库提供的 `_post` 生成签名和请求。 |
| `23103` | 部分明细接口的单次时间范围不能超过一天；`cloud_sync` 已按天请求。 |
| 步数成功但没有 `ssoid` | 确认登录账号和健康云服务状态，再重新执行认证生成脚本；脚本不会保存不完整配置。 |

## 本次验证记录

2026-10-20，在 Android 15 模拟器、国内版 `com.heytap.health` 已登录且健康云服务开启的状态下，使用应用私有账号文件生成 `auth.json`。`cloud_status` 显示认证就绪；步数和体重只读云端请求均返回 `errorCode=0`。认证值和健康记录未纳入本文。
