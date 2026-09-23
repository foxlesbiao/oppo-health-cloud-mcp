# oppo-health-cloud-mcp

OPPO 健康（欢太健康）云端 API 直连客户端 + MCP server。无需 root / LSPosed，从云端拉取你自己的健康明细数据（心率/血氧/步数/睡眠/体重/App使用/跌倒/insight），供任意 AI agent 分析。

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

1. 抓包一次拿三件套（mitmproxy 挂手机，开健康 App 同步）：
   - `token` 头（`ACCESS_` 开头）
   - `token-auth-id` 头
   - `ssoid`（virtual-ssoid / userTagId）
2. 写入同目录 `auth.json`（勿提交）：
   ```json
   {"token": "ACCESS_...", "token_auth_id": "...", "ssoid": "..."}
   ```
3. 注册 MCP (stdio)：`python3 cloud_mcp.py`
4. 工具：
   - `cloud_sync(metric, days)` — 云端拉取 → 本地 SQLite 缓存
   - `cloud_query(metric, date)` — 查缓存
   - `cloud_analyze(days)` — 周期环比 + 异常标记
   - `cloud_status` — 自检

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
