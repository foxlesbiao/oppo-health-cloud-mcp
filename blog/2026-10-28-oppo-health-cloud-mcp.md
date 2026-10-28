# 让 AI 读取 OPPO 健康：我写了一个健康云 MCP

最近我把 OPPO 健康（欢太健康）的云端只读接口包成了一个 MCP server，项目叫
[oppo-health-cloud-mcp](https://github.com/foxlesbiao/oppo-health-cloud-mcp)。它的目标很朴素：让支持 MCP 的 AI 客户端可以安全地读取**本人账号**的健康数据，然后在本地做趋势分析，而不是每次都让我在 App 里来回点。

先说边界：这是学习和研究用的项目，不是 OPPO 官方 API，也没有接入任何修改数据的接口。它只应该用来读取自己的健康记录。健康数据很敏感，不适合部署成多人共享服务。

## 它能做什么

项目目前提供四个 MCP 工具：

- `cloud_sync(metric, days)`：从健康云拉取数据并写入本地 SQLite。
- `cloud_query(metric, date)`：查询本地缓存。
- `cloud_analyze(days)`：生成最近一段时间与上一段时间的环比分析。
- `cloud_status`：检查认证文件和缓存状态。

当前暴露了 67 个 metric：65 个独立指标，加上 `stress` 和 `physical_mental` 两个组合指标。覆盖心率、血氧、血压、血糖、HRV、呼吸率、步数、睡眠、腕温、ECG、打鼾/OSA、压力、身心健康、女性健康、体重、听力、颈椎训练、日照、应用使用等类别。

当然，接口存在不代表账号里一定有数据。比如某些健康功能没有开启，或者设备没有记录过这类数据，`cloud_sync` 成功返回空集也很正常。

## 登录方式

我做了两个方向：

1. **实验性登录器**：`oppo_login.py` 支持手机号验证码登录，如果服务端触发二次认证，会继续要求身份证后 6 位。成功后会换取健康包级 token，并写入本地 `auth.json`。
2. **已登录 App 凭据提取**：通过单独文档描述如何从本人设备上的 OPPO 健康 App 私有账号文件读取凭据，再通过只读接口获取 `ssoid`。这条路需要 root/ADB。

登录器不会回显手机号、验证码、身份证后 6 位或 token；账号刷新 token 也不会写入磁盘。`auth.json` 使用 `0600` 权限保存。

为了避免多个账号共用同一个设备身份，登录器默认为每次登录生成随机设备 ID，也可以用参数或环境变量固定：

```bash
python3 oppo_login.py login \
  --device-id 0123456789abcdef0123456789abcdef \
  --sdk-device-id fedcba9876543210fedcba9876543210
```

多账号本机隔离时，还可以给每个账号配置独立的认证和缓存文件：

```bash
export OPPO_HEALTH_AUTH_FILE=/secure/path/account-a-auth.json
export OPPO_HEALTH_CACHE_DB=/secure/path/account-a-cache.db
```

## MCP 接入

安装依赖：

```bash
python3 -m pip install "mcp[cli]" requests pycryptodome
```

在 MCP 客户端里注册 stdio server：

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

然后就可以这样用：

```text
cloud_status
cloud_sync(metric="steps", days=1)
cloud_query(metric="steps", date="2026-10-28")
cloud_analyze(days=7)
```

## 实现上比较麻烦的地方

健康云接口的请求签名和网关行为都比较挑剔。简单概括：

- 请求签名需要复刻客户端逻辑。
- Python `urllib/requests` 会被网关的 TLS 指纹策略拦截，所以核心请求走 `curl` 子进程。
- 一些明细接口单次范围限制在一天以内，MCP 内部会按天或版本游标分页。
- 部分指标需要先查版本列表，再按版本读取详情。
- 加多余请求头反而可能破坏签名校验，所以请求头集合必须保持精确。

常见错误也分了几层：网关层、验签层、业务层。比如 `10103` 多半是网关/TLS 指纹问题，`10100` 多半是请求头或签名输入被改动，`23103` 是单次时间范围超过限制。

## 数据安全

`auth.json` 和 `cloud_cache.db` 都在 `.gitignore` 里，但它们本质上等同于敏感凭据和敏感健康数据。不要提交、截图、粘贴到群里，也不要把它们放进公共目录。

如果凭据泄露，应该在欢太账号或 OPPO 健康里退出登录、修改密码，并尽快清理本地文件。

## 后续

现在基础同步、查询和分析已经可用，登录流程也跑通了。后面更适合做的是把 `cloud_analyze` 的报告格式再打磨一下，让 AI 更稳定地输出“周期变化、异常点和建议”，而不是把原始健康数据全部丢给模型。

项目地址：

<https://github.com/foxlesbiao/oppo-health-cloud-mcp>
