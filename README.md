# OPPO Health Cloud MCP

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

OPPO 健康（欢太健康）云端只读客户端和 MCP server。它把你自己账号里的心率、血氧、步数、睡眠、体重、腕温、HRV、压力、身心健康等数据同步到本地 SQLite，并暴露给支持 MCP 的 AI 客户端查询和分析。

> **仅供学习和研究，只能访问本人账号数据。** 这不是 OPPO 官方 API，服务端返回结构可能随 App 版本变化。请勿用于访问他人健康数据、自动化滥用或商业用途。

实验性登录器 `oppo_login.py` 不需要 root。认证手册中的“从已登录 App 私有文件读取凭据”方式则需要 root/ADB。

## 功能

- **MCP stdio server**：提供 `cloud_sync`、`cloud_query`、`cloud_analyze` 和 `cloud_status` 四个工具。
- **67 个指标**：65 个独立指标，以及 `stress`、`physical_mental` 两个组合指标。
- **本地缓存**：云端数据写入 `cloud_cache.db`，后续查询不重复请求云端。
- **直连签名请求**：复刻 OPPO 健康云客户端的 HTTP 请求签名，通过 `curl` 发送以兼容网关 TLS 指纹。
- **实验性账号登录**：支持手机验证码登录、可选二次认证和健康云 token 换取。

## 环境要求

- Python 3.10 或更高版本
- 系统可用 `curl`
- 支持 stdio MCP 的客户端

安装 Python 依赖：

```bash
python3 -m pip install "mcp[cli]" requests pycryptodome
```

## 快速开始

### 1. 生成 `auth.json`

推荐先尝试实验性登录器：

```bash
python3 oppo_login.py login
```

它会完成欢太账号验证码登录、可选二次认证、健康包 token 换取和健康云账号登录，最后写入 `auth.json`。如果服务端没有触发二次认证，就不需要身份证信息。

`oppo_login.py` 会隐藏手机号、验证码、身份证后 6 位和 token 输入；账号刷新 token 不会写入磁盘。`auth.json` 以 `0600` 权限保存。

另一种方式是从本人已登录 OPPO 健康 App 的私有账号文件读取凭据，再通过只读接口获取 `ssoid`。详细步骤见 [OPPO健康国内版云端MCP认证手册](OPPO健康国内版云端MCP认证手册.md)。最小 `auth.json` 结构是：

```json
{
  "token": "ACCESS_...",
  "token_auth_id": "...",
  "ssoid": "..."
}
```

`token`、`token_auth_id` 和 `ssoid` 必须来自同一个账号。不要提交或粘贴这个文件。

### 2. 注册 MCP server

`cloud_mcp.py` 使用 stdio 传输。在 MCP 客户端中把它配置为本机 Python 启动：

```json
{
  "mcpServers": {
    "oppo-health-cloud": {
      "command": "python3",
      "args": ["/absolute/path/to/oppo-health-cloud-mcp/cloud_mcp.py"]
    }
  }
}
```

Windows 下把 `command` 改为本机 Python 解释器路径，例如 `python.exe`。

### 3. 验证和同步

在 MCP 客户端中调用：

```text
cloud_status
cloud_sync(metric="steps", days=1)
cloud_query(metric="steps", date="2026-10-28")
cloud_analyze(days=7)
```

也可以在仓库目录中做本地自检：

```bash
python3 -c "from cloud_mcp import cloud_status; print(cloud_status())"
```

`cloud_status` 只检查认证文件和缓存状态；真正的云端可用性还需要调用一次只读同步接口。

## MCP 工具

| 工具 | 读取 | 说明 |
|---|---|---|
| `cloud_sync(metric, days=7)` | 读/写 | 拉取云端数据并写入本地 SQLite。部分接口内部按天或版本游标分页。 |
| `cloud_query(metric, date=None)` | 只读 | 查询本地缓存。`date` 支持 `YYYYMMDD` 或 `YYYY-MM-DD`。 |
| `cloud_analyze(days=7)` | 只读 | 汇总最近周期与上一周期，输出心率、血氧、步数、睡眠等趋势和异常标记。 |
| `cloud_status` | 只读 | 检查 `auth.json` 和 `cloud_cache.db` 状态。 |

`stress` 和 `physical_mental` 是组合指标；查询结果会按子数据集分组。`metric` 参数通过 MCP schema 提供完整枚举。

## 支持的数据范围

常用类别包括心率、血氧、血压、血糖、HRV、呼吸率、步数、运动、睡眠、腕温、ECG、打鼾/OSA、压力、身心健康、女性健康、体重、听力、颈椎训练、日照和应用使用。

<details>
<summary><strong>完整指标表</strong></summary>

| 类别 | MCP metric | 缓存内容概要 |
|---|---|---|
| 心率 | `heart_rate`, `heart_rate_detail`, `heart_rate_stat`, `heart_rate_warning` | 心率明细、日统计和预警记录 |
| 血氧 | `blood_oxygen`, `blood_oxygen_detail`, `blood_oxygen_stat`, `blood_oxygen_warning`, `blood_oxygen_origin` | 血氧明细、统计、预警和设备原始记录 |
| 血压 | `blood_pressure`, `blood_pressure_stat` | 血压明细和统计 |
| 血糖 | `blood_sugar`, `blood_sugar_stat`, `blood_sugar_warning` | 血糖明细、统计和预警 |
| 步数 | `steps`, `steps_detail`, `steps_stat` | 步数明细、距离、卡路里、时长和日统计 |
| 睡眠 | `sleep`, `sleep_stat`, `sleep_status`, `sleep_index`, `sleep_rr`, `sleep_advice`, `sleep_hr_stat` | 睡眠统计、阶段、指数、RR 间隔、建议和睡眠心率 |
| HRV / 压力 | `hrv`, `stress_detail`, `stress_stat`, `stress` | HRV、压力明细和压力统计 |
| 身心健康 | `physical_mental`, `physical_mental_detail`, `physical_mental_stat`, `physical_mental_achievement` | 明细、统计、目标和成就 |
| 呼吸 / 心血管 | `breath_rate`, `atrial_fibril`, `atrial_fibril_warning`, `cardiovascular` | 呼吸率、房颤和心血管评估 |
| 腕温 / ECG | `wrist_temperature`, `wrist_temperature_detail`, `ecg` | 腕温统计/明细和心电图元数据 |
| 打鼾 / OSA | `snore_osa_detail`, `snore_osa_sum`, `snore_env_noise`, `snore_feature`, `sensor_osa`, `snore_stat` | OSA 模型、环境噪声、鼾声特征和统计 |
| 运动 | `sport_stat`, `sport_record`, `sport_file`, `sport_goal`, `exercise_intensity` | 运动统计、版本、加密文件、目标和强度 |
| 体重 | `weight`, `weight_target` | 体重记录和体重目标 |
| 其他健康记录 | `tumble`, `sedentary`, `hearing`, `hearing_stat`, `cervical_stat`, `cervical_action`, `sunshine`, `sunshine_stat`, `vitamin` | 跌倒、久坐、听力、颈椎、日照和维生素 |
| 女性健康 | `physiological_cycle`, `physiological_symptoms`, `ovulation` | 周期、症状和排卵信息 |
| 应用使用 | `app_usage`, `app_usage_detail` | 应用使用统计和明细 |
| 健康洞察 | `insight` | 服务端返回的近期健康洞察数据 |

</details>

接口存在不代表账号一定有对应数据；成功返回空集只说明本次没有记录。`wrist_temperature` 是相对个人基线的统计，不是体温计绝对体温。

`sport_file` 需要应用运行时生成的 `encryptKeyEnc`，当前项目尚未实现该密钥生成，因此会返回 `encrypt_key_enc_required`。`sport_record` 只是云端运动文件的版本索引，不是解密后的轨迹。

## 项目结构

```text
cloud_mcp.py              MCP server、健康云签名请求、SQLite 缓存
oppo_login.py             实验性手机验证码登录和 token 换取
oppo_sign.py              健康云请求签名辅助
OPPO健康国内版云端MCP认证手册.md  从已登录 App 私有文件读取凭据的详细手册
auth.json                 本地凭据，已被 git 忽略
cloud_cache.db            本地健康数据缓存，已被 git 忽略
```

## 实现说明

- 健康云接口由 `cloud_mcp.py` 使用静态应用签名常量构造请求，并通过 `curl` 发送；没有实现账号注册、数据修改或他人数据访问。
- 明细和统计接口会根据服务端要求先请求版本列表，再读取版本详情；`cloud_sync` 内部处理分页和单日范围限制。
- SQLite 主表 `cloud_data` 使用 `(metric, date)` 作为主键，重复同步会替换同一条记录。
- 登录器复刻欢太账号 OpenSDK 的加密信封和请求头流程，仅在服务端要求时进入二次认证。

## 常见问题

| 现象 / 错误码 | 处理 |
|---|---|
| `10101` | token 无效或被截断；重新登录，不要手动修改 `token`。 |
| `10103` | 网关 TLS/请求指纹拦截；保留 `cloud_mcp.py` 的 `curl` 请求路径，不要改成 `urllib`。 |
| `10100` | 请求头或签名输入被修改；使用仓库现有 `_post`，不要随意增删头。 |
| `23103` | 单次时间范围超过限制；`cloud_sync` 已按天处理，自定义请求时缩小范围。 |
| `encrypt_key_enc_required` | `sport_file` 需要应用运行时密钥，当前未支持。 |
| `2510101` | 短时间内验证码发送达到服务端上限；等待后再试。 |
| 登录页提示无网络 | 关闭系统代理和 TLS 解密工具后重试。 |

## 安全与隐私

- 只把 `auth.json` 和 `cloud_cache.db` 放在本机；两者都已加入 `.gitignore`。
- 不要提交或分享 `auth.json`、HAR、代理日志、应用私有账号文件、SQLite 缓存或包含健康读数的 MCP 输出。
- `auth.json` 和缓存数据库等同敏感凭据。泄露后应尽快在 OPPO 健康/欢太账号中退出登录或修改密码。
- 本项目不适合部署成多人共享服务；当前设计假设单人本机使用。

## License

MIT
