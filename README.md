# oppo-health-cloud-mcp

OPPO 健康（欢太健康）云端 API 直连客户端 + MCP server。无需 root / LSPosed，从云端拉取你自己的健康明细数据（心率/血氧/步数/睡眠/体重/腕温/HRV/压力/身心健康/呼吸率等），供任意 AI agent 分析。

> ⚠️ **仅供本人学习研究**。导出的是你自己的健康数据，请勿用于侵犯他人隐私或商用。

## 原理

OPPO 健康云 API（`sport.health.heytapmobi.com/sporthealth/`）的请求签名是 **HMAC-SHA256 + 静态密钥**：

```
canonical = sorted(k=v&)[:-1] + body去空白
signature = base64(HmacSHA256(httpSecret, canonical))
httpSecret = XXTEA解密(BuildConfig.httpSecret常量, 两个UUID逐字符交错)
```

密钥是 APK `BuildConfig` 里的**静态常量**（非服务端协商），因此一次逆向、永久复刻，无需真机签名代理。50/50 抓包对拍验证通过。

## 使用

1. 按[国内版 OPPO 健康认证手册](OPPO健康国内版云端MCP认证手册.md)获取三件套。已验证流程从应用私有账号文件读取 `token` 和 `token-auth-id`，再通过只读云端请求获取 `ssoid`，不需要 HTTPS 中间人抓包。
2. 写入同目录 `auth.json`（勿提交）：
   ```json
   {"token": "ACCESS_...", "token_auth_id": "...", "ssoid": "..."}
   ```
3. 注册 MCP (stdio)：`python3 cloud_mcp.py`
4. 工具：
   - `cloud_sync(metric, days)` — 云端拉取 → 本地 SQLite 缓存
   - `cloud_query(metric, date)` — 查缓存，`date` 支持 `YYYYMMDD` 或 `YYYY-MM-DD`
   - `cloud_analyze(days)` — 周期环比 + 异常标记
   - `cloud_status` — 自检

`wrist_temperature` 返回腕部温度统计。数值表示相对个人基线的变化，不是体温计测得的绝对体温。

### 新增健康指标

| 指标 | MCP metric | 缓存内容 |
|---|---|---|
| HRV | `hrv` | 心率变异性明细，包含 `heartRateVarValue`、`startTimestamp`、`endTimestamp` 等字段 |
| 压力 | `stress` | `stress_detail` 压力明细（`stressValue`、`stressType`、`rmssd`、`sdnn` 等）和 `stress_stat` 日统计 |
| 身心健康 | `physical_mental` | `physical_mental_detail` 明细、`physical_mental_stat` 日统计、`physical_mental_achievement` 每日目标与成就 |
| 呼吸率 | `breath_rate` | 呼吸率记录，外层按时间段保存，逐条读数位于嵌套 `dataList`（含 `respiratoryRate`） |

压力与身心健康的 `cloud_query` 结果按子数据集分组。若 HRV 或压力独立接口没有记录，MCP 会从身心健康明细的 `hrv` / `stress` 子项生成对应记录，并标注 `source: physical_mental_detail`，同时保留原始 `startTimeOffset`。调用 `cloud_sync` 时，`days` 控制 HRV/呼吸率的按日拉取范围，并筛选压力和身心健康结果的近期记录；版本游标接口仍会按服务端分页规则遍历版本。

## 踩坑记录（重要）

| 坑 | 结论 |
|---|---|
| python urllib/requests 全部 403 `10103` | **TLS 指纹拦截**。必须 curl 子进程（okhttp 指纹相近），真假 token 差分法会失效 |
| 加了 `virtual-ssoid` 头 / gzip 头 → `10100` | **多余头参与验签**。只发精确 HAR 头集，ssoid 走 body 的 userTagId |
| v5 pull* 端点回 `23103` | 单次范围 ≤1 天，按天循环 |
| steps 响应是 dict，心率/血氧是数组 | 解析需兼容两种结构 |

错误码分层：`10103`=网关层(TLS/头)，`10100`=验签层(头污染)，`23103`=业务层(范围)，`0`=成功。

## License

MIT
