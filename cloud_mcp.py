#!/usr/bin/env python3
"""OPPO 健康云同步数据 MCP server — 独立完整，不依赖 hook/sink/手机。

用法:
1. 抓包一次获得以下值, 写入同目录 auth.json:
   {
     "token": "ACCESS_....",            # accountsdk token (抓包 token 头)
     "token_auth_id": "Fcpm...==",      # token-auth-id 头 (= usercenter.db deviceId)
     "ssoid": "<your_virtual_ssoid>"     # virtual-ssoid (userTagId)
   }
   token 过期后重抓一次即可。签名密钥内嵌, 无需其他配置。
2. 注册 MCP (stdio): <python> cloud_mcp.py
3. 工具: cloud_sync(拉明细), cloud_query(查本地缓存), cloud_status(自检)
"""
import base64, datetime, hashlib, hmac, json, os, sqlite3, struct, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.join(HERE, "auth.json")
CACHE_DB = os.path.join(HERE, "cloud_cache.db")
HOST = "https://sport.health.heytapmobi.com/sporthealth/"

APPID = "M2QfBThPRpGcGovBva3ENX"
APP_PACKAGE = "com.heytap.health"
APP_KEY_VERSION = "1732499446015"
APP_VERSION = "6091900"
VERSION_NAME = "6.9.19_b95456c_260918"

ENDPOINTS = {
    "heart_rate":  ["v5/c2s/health/heartRate/pullHeartRateDetailData"],
    "blood_oxygen":["v5/c2s/health/bloodOxygen/pullBloodOxygenDetailData"],
    "steps":       ["v5/c2s/sport/steps/pullStepsDetailData"],
    "sleep":       ["v5/c2s/health/sleep/querySleepDayStatData"],
    "tumble":      ["v5/c2s/health/tumble/pullTumbleRecordData"],
    "app_usage":   ["v5/c2s/health/pullAppUsageStatPageList"],
    "insight":     ["v5/c2s/insight/queryRecentData"],
    "weight":      ["v1/c2s/health/weight/querySignedWeight"],
    "wrist_temperature": ["v5/c2s/health/wrist/temperature/pullStatVersionPageData"],
}

# ---------- 签名 (pk9 逆向, 50/50 对拍通过, 详见 oppo_sign.py) ----------
_DYN = "e4f5d127-d57d-4d97-a1e7-e762a13f8793"
_STAT = "a2a9725d-fb95-be34-160ad21378a1"
_ENC = "BKQyb7r9VBOiFVGONfdoaFhuyDkRgxLxN7L46w=="
_DELTA = 0x9E3779B9

def _h(b, il=False):
    n = (len(b)+3)//4
    v = [0]*(n+1) if il else [0]*n
    if il: v[n] = len(b)
    for i,c in enumerate(b): v[i>>2] |= c << ((i&3)<<3)
    return v

def _g(v, il):
    ln = v[-1] if il else len(v)*4
    n = len(v)-1 if il else len(v)
    return bytes(((v[i>>2] >> ((i&3)<<3)) & 0xFF) for i in range(min(ln, n*4)))

def _mx(i,i2,i3,i4,i5,k):
    return ((i^i2) + (k[(i4&3)^i5]^i3)) ^ (((i3>>5)^(i2<<2)) + ((i2>>3)^(i3<<4)))

def _http_secret():
    key = ''.join(a+b for a,b in zip(_DYN,_STAT)).encode()
    v = _h(base64.b64decode(_ENC)); k = _h(key[:16].ljust(16, b' '))
    n = len(v)-1
    s = (((52//(n+1))+6)*_DELTA) & 0xFFFFFFFF
    while s:
        e=(s>>2)&3; p=n; i4=v[0]
        while p>0:
            i4=(v[p]-_mx(s,i4,v[p-1],p,e,k))&0xFFFFFFFF; v[p]=i4; p-=1
        i4=(v[0]-_mx(s,i4,v[n],0,e,k))&0xFFFFFFFF; v[0]=i4
        s=(s-_DELTA)&0xFFFFFFFF
    return _g(v, True)

_HTTP_SECRET = _http_secret()

def _sign(hdrs, body):
    m = dict(hdrs)
    m.update({'os-type':'1', 'lang':'zh-CN', 'risk-sign':'2'})
    canonical = ''.join(f'{k}={v}&' for k,v in sorted(m.items()))[:-1]
    if body:
        canonical += body.replace(' ','').replace('\n','').replace('\r','')
    return base64.b64encode(hmac.new(_HTTP_SECRET, canonical.encode(), hashlib.sha256).digest()).decode()

def _new_nonce(): return os.urandom(16).hex()
def _new_ts(): return str(int(time.time()*1000))

def _load_auth():
    with open(AUTH_FILE) as f:
        a = json.load(f)
    assert a.get("token"), "auth.json 缺 token"
    return a

def _post(path, body_obj, auth, timeout=20):
    """用curl发请求 — python urllib的TLS指纹被网关10103拒绝(2026-09-22实测), curl能过"""
    body = json.dumps(body_obj, separators=(',',':'))
    hdrs = {
        'appid': APPID, 'app-package': APP_PACKAGE,
        'nonce': _new_nonce(), 'timestamp': _new_ts(),
        'token': auth['token'], 'token-auth-id': auth['token_auth_id'],
        'app-version': APP_VERSION,
    }
    sig = _sign(hdrs, body)
    cmd = ['curl','-s','-m',str(timeout),'-X','POST', HOST + path,
        '-H','Content-Type: application/json; charset=UTF-8',
        '-H','User-Agent: okhttp/4.9.3.7',
        '-H',f'app-key-version: {APP_KEY_VERSION}',
        '-H',f'app-package: {APP_PACKAGE}',
        '-H',f'appid: {APPID}',
        '-H',f'app-version: {APP_VERSION}',
        '-H',f'versionName: {VERSION_NAME}',
        '-H','lang: zh-CN','-H','os-type: 1','-H','risk-sign: 2','-H','t-route-tag:',
        '-H',f'nonce: {hdrs["nonce"]}',
        '-H',f'timestamp: {hdrs["timestamp"]}',
        '-H',f'token: {auth["token"]}',
        '-H',f'token-auth-id: {auth["token_auth_id"]}',
        '-H',f'signature: {sig}',
        '--data-binary', body]
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"http_error": 0, "body": r.stdout[:500] or r.stderr[:200]}

def _db():
    con = sqlite3.connect(CACHE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS cloud_data(
        metric TEXT, date TEXT, payload TEXT, fetched_at INTEGER,
        PRIMARY KEY(metric, date))""")
    return con

def _cache(metric: str, items: list) -> int:
    con = _db(); now = int(time.time()); n = 0
    for it in items:
        d = str(it.get("date") or it.get("dataCreatedTimestamp") or it.get("startTimestamp")
                or it.get("measurementTime") or it.get("modifiedTimestamp") or now)
        con.execute("INSERT OR REPLACE INTO cloud_data VALUES(?,?,?,?)",
                    (metric, d, json.dumps(it), now))
        n += 1
    con.commit(); con.close()
    return n

def cloud_sync(metric: str, days: int = 7) -> dict:
    """从云端拉取指定指标, 写入本地缓存.
    pull端点限制单次范围≤1天(23103), 内部按天循环.
    sleep: version游标全量(单条1请求, 仅增量ts); app_usage: date+queryFlag; weight: userTagId+pageSize."""
    auth = _load_auth()
    eps = ENDPOINTS.get(metric)
    if not eps:
        return {"error": f"unknown metric {metric}, 可用: {list(ENDPOINTS)}"}
    ep = eps[0]
    items = []
    if metric == "sleep":
        # version 游标向前翻页(queryFlag0+cursor, 每300条/hasMore), 再逐ts拉记录
        all_ts = []
        cursor = 0
        while True:
            b = (_post("v3/c2s/health/sleep/querySleepDayStatVersion",
                       {"queryFlag": 0, "modifiedTimestamp": cursor}, auth).get("body") or {})
            lst = b.get("modifiedTimestampList") or []
            if not lst:
                break
            all_ts += lst
            new_cursor = lst[-1]
            if new_cursor <= cursor or not b.get("hasMore"):
                break
            cursor = new_cursor
        for ts in all_ts:
            r = _post("v5/c2s/health/sleep/querySleepDayStatData",
                      {"queryFlag": 1, "modifiedTimestamp": ts}, auth)
            if r.get("errorCode") == 0 and isinstance(r.get("body"), list):
                items.extend(r["body"])
    elif metric == "wrist_temperature":
        # 统计接口使用修改时间版本游标；按版本范围拉取每日腕部温度统计。
        all_ts = []
        cursor = 0
        while True:
            r = _post(
                "v4/c2s/health/wrist/temperature/queryWristTemperatureStatVersion",
                {"queryFlag": 0, "modifiedTimestamp": cursor}, auth
            )
            if r.get("errorCode") != 0:
                return {"error": "wrist temperature version query failed",
                        "errorCode": r.get("errorCode")}
            b = r.get("body") or {}
            page = b.get("modifiedTimestampList") or []
            if not page:
                break
            all_ts.extend(page)
            new_cursor = page[-1]
            if new_cursor <= cursor or not b.get("hasMore"):
                break
            cursor = new_cursor
        if all_ts:
            r = _post(
                ep,
                {"startModifiedTimestamp": min(all_ts),
                 "endModifiedTimestamp": max(all_ts)}, auth
            )
            if r.get("errorCode") != 0:
                return {"error": "wrist temperature data query failed",
                        "errorCode": r.get("errorCode")}
            b = r.get("body") or {}
            if isinstance(b, dict):
                items.extend(b.get("dataList") or [])
    elif metric == "app_usage":
        import datetime as _dt
        today = _dt.date.today()
        for back in range(max(days, 1)):
            dint = int((today - _dt.timedelta(days=back)).strftime("%Y%m%d"))
            for flag in (0, 1):
                r = _post(ep, {"date": dint, "queryFlag": flag}, auth)
                b = r.get("body") or {}
                if r.get("errorCode") == 0:
                    items.extend(b.get("dataList") or [])
    elif metric == "tumble":
        import datetime as _dt
        today = _dt.date.today()
        for back in range(max(days, 1)):
            end = int(_dt.datetime.combine(today - _dt.timedelta(days=back), _dt.time.min).timestamp()*1000)
            r = _post(ep, {"timestamp": end}, auth)
            b = r.get("body") or {}
            if r.get("errorCode") == 0:
                items.extend(b.get("tumbleRecordList") or [])
    elif metric == "insight":
        r = _post("v5/c2s/insight/queryRecentData", {}, auth)
        if r.get("errorCode") == 0 and r.get("body"):
            items.append(r["body"])
    elif metric == "weight":
        r = _post(ep, {"userTagId": auth.get("ssoid"),
                       "pageSize": 100, "modifiedTime": 0, "order": 1}, auth)
        if r.get("errorCode") == 0 and isinstance(r.get("body"), list):
            items.extend(r["body"])
    else:
        today0 = int(datetime.datetime.combine(datetime.date.today(), datetime.time.min).timestamp()*1000)
        for d in range(days):
            start = today0 - (days-1-d)*86400000
            body = {"startTimestamp": start, "endTimestamp": start + 86399999}
            r = _post(ep, body, auth)
            b = r.get("body")
            if r.get("errorCode") == 0 and isinstance(b, list):
                items.extend(b)
            elif r.get("errorCode") == 0 and isinstance(b, dict):
                for v in b.values():
                    if isinstance(v, list): items.extend(v)
            elif r.get("errorCode") != 0:
                return {"error": f"day {d} failed", "detail": r}
    n = _cache(metric, items)
    if metric == "wrist_temperature":
        dates = sorted({str(item.get("date")) for item in items if item.get("date") is not None})
        return {"metric": metric, "endpoint": ep, "rows_cached": n, "dates": dates}
    return {"metric": metric, "endpoint": ep, "rows_cached": n,
            "raw_sample": items[:2]}

def cloud_query(metric: str, date: str = None) -> dict:
    """查询本地缓存 (先 sync 再 query). date=YYYYMMDD 可选."""
    con = _db()
    if date:
        rows = con.execute("SELECT payload FROM cloud_data WHERE metric=? AND date=?",
                           (metric, date)).fetchall()
    else:
        rows = con.execute("SELECT date, payload FROM cloud_data WHERE metric=? ORDER BY date DESC LIMIT 100",
                           (metric,)).fetchall()
    con.close()
    return {"metric": metric, "count": len(rows),
            "data": [json.loads(r[0] if len(r) == 1 else r[1]) for r in rows]}

_KCAL = 1000  # steps.calories 原始值单位为毫千卡, /1000 = kcal

def _day_rows(con, metric):
    """yield (local_date_str 'YYYY-MM-DD', payload_dict)"""
    for (p,) in con.execute("SELECT payload FROM cloud_data WHERE metric=?", (metric,)):
        d = json.loads(p)
        ts = d.get("dataCreatedTimestamp") or d.get("startTimestamp") or d.get("measurementTime")
        if ts:
            yield datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"), d
        elif d.get("date"):
            s = str(d["date"])
            yield f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s, d

def cloud_analyze(days: int = 7) -> dict:
    """聚合分析本地缓存: 本周期 vs 上一周期环比 + 异常标记. 需先 cloud_sync 落数据."""
    con = _db()
    today = datetime.date.today()
    cur = {(today - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)}
    prev = {(today - datetime.timedelta(days=days + i)).strftime("%Y-%m-%d") for i in range(days)}

    def bucket(metric, fn, daily=None):
        """fn(payload_dict)->value or None. daily: 指标值提取函数, 按天求和再对天取日均(steps等累加型).
        默认逐点均值(hr等瞬时型). 返回 (本周期日均, 上周期日均, 覆盖天数)"""
        per_day = {}
        for day, d in _day_rows(con, metric):
            v = fn(d)
            if v is None: continue
            per_day.setdefault(day, []).append(v)
        agg = (lambda vs: sum(vs)) if daily else (lambda vs: sum(vs) / len(vs))
        dayvals = {k: agg(v) for k, v in per_day.items()}
        avg = lambda x: sum(x) / len(x) if x else None
        a = [v for k, v in dayvals.items() if k in cur]
        b = [v for k, v in dayvals.items() if k in prev]
        return avg(a), avg(b), len({k for k in dayvals if k in cur})

    hr_avg,  hr_prev,  hr_days  = bucket("heart_rate", lambda d: d.get("heartRateValue") if d.get("heartRateType") == 0 else None)
    spo2,    spo2_prev, spo2_days = bucket("blood_oxygen", lambda d: d.get("bloodOxygenSaturationValue") if d.get("bloodOxygenSaturationType") == 1 else None)
    steps_a, steps_prev, steps_days = bucket("steps", lambda d: d.get("steps") or 0, daily=True)
    kcal_a,  kcal_prev, _        = bucket("steps", lambda d: (d.get("calories") or 0) / _KCAL, daily=True)
    # sleep: 同一date取totalSleepTime最大那条(多设备/重复)
    sleep_acc = {}
    for day, d in _day_rows(con, "sleep"):
        v = d.get("totalSleepTime")
        if v: sleep_acc[day] = max(sleep_acc.get(day, 0), v)
    rem_acc, deep_acc = {}, {}
    for day, d in _day_rows(con, "sleep"):
        if d.get("totalREMSleepTime"): rem_acc[day] = max(rem_acc.get(day, 0), d["totalREMSleepTime"])
        if d.get("totalDeepSleepTime"): deep_acc[day] = max(deep_acc.get(day, 0), d["totalDeepSleepTime"])
    def davg(acc):
        a = [v for k, v in acc.items() if k in cur]; b = [v for k, v in acc.items() if k in prev]
        f = lambda x: sum(x) / len(x) if x else None
        return f(a), f(b), len(a)
    sleep_a, sleep_p, sleep_days = davg(sleep_acc)
    rem_a,   rem_p,   _         = davg(rem_acc)
    deep_a,  deep_p,  _         = davg(deep_acc)
    wt = [json.loads(p) for (p,) in con.execute("SELECT payload FROM cloud_data WHERE metric='weight'")]
    wt_kg = sorted(((d.get("measurementTime", 0), int(d.get("weight", 0)) / 1000) for d in wt), reverse=True)
    con.close()

    def row(name, a, p, unit="", good=None, warn=None):
        if a is None: return f"  {name}: 无数据"
        delta = f"{a - p:+.1f}" if p is not None else "—"
        flag = ""
        if good:  # (lo, hi) 区间外标⚠
            lo, hi = good
            if a < lo or a > hi: flag = " ⚠️"
        if warn is not None and a < warn: flag = " ⚠️"
        return f"  {name}: {a:.1f}{unit} (上期 {'—' if p is None else f'{p:.1f}{unit}'}, {delta}){flag}"

    lines = [f"## OPPO健康分析 近{days}天 (vs 上{days}天)"]
    lines.append(row("心率均值", hr_avg, hr_prev, "bpm", good=(60, 100)))
    lines.append(row("血氧均值", spo2, spo2_prev, "%", good=(95, 100)))
    lines.append(row("日均步数", steps_a, steps_prev, "步", warn=6000))
    lines.append(row("日均千卡", kcal_a, kcal_prev, "kcal"))
    lines.append(row("睡眠时长", sleep_a, sleep_p, "min", good=(420, 600)))
    lines.append(row("深睡", deep_a, deep_p, "min", good=(60, 180)))
    lines.append(row("REM", rem_a, rem_p, "min", good=(90, 180)))
    if wt_kg:
        lines.append(f"  最新体重: {wt_kg[0][1]:.1f}kg ({datetime.datetime.fromtimestamp(wt_kg[0][0]/1000).strftime('%m-%d')})")
    miss = [m for m, n in [("睡眠", sleep_days), ("心率", hr_days), ("血氧", spo2_days), ("步数", steps_days)] if n == 0]
    if miss: lines.append(f"  ⚠️ 无数据: {', '.join(miss)} (先跑 cloud_sync)")
    lines.append("  口径: 步数/千卡=全天各模式累加; 睡眠=同日取最长一条; 心率=type0单点均值非静息心率")
    return {"report": "\n".join(lines), "days": days,
            "coverage": {"heart_rate_days": hr_days, "spo2_days": spo2_days,
                         "steps_days": steps_days, "sleep_days": sleep_days}}

def cloud_status() -> dict:
    """检查 auth.json 和缓存状态."""
    ok = os.path.exists(AUTH_FILE)
    con = _db()
    stats = dict(con.execute("SELECT metric, COUNT(*) FROM cloud_data GROUP BY metric").fetchall())
    con.close()
    return {"auth_ready": ok, "cache": stats,
            "note": "auth.json 需含 token/token_auth_id/ssoid (抓包一次获取)"}

if __name__ == "__main__":
    # 自检: 签名对拍
    samples_path = os.path.join(HERE, "sign_samples.json")
    if os.path.exists(samples_path):
        samples = json.load(open(samples_path))
        ok = 0
        for s in samples:
            hdrs = {k: s['headers'][k] for k in ('appid','app-package','nonce','timestamp','token','token-auth-id','app-version')}
            if _sign(hdrs, s.get('body','')) == s['signature']:
                ok += 1
        print(f"签名自检: {ok}/{len(samples)}", file=__import__('sys').stderr)
        assert ok == len(samples)

    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("oppo_health_cloud")
    mcp.tool()(cloud_sync)
    mcp.tool()(cloud_query)
    mcp.tool()(cloud_analyze)
    mcp.tool()(cloud_status)
    mcp.run()
