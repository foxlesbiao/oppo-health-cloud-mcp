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
3. 工具: cloud_sync(拉明细并写缓存), cloud_query(查缓存), cloud_analyze(周期分析), cloud_status(自检)
"""
import base64, datetime, hashlib, hmac, json, os, sqlite3, struct, time, urllib.request, urllib.error
from typing import Literal

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
    "heart_rate_detail": ["v5/c2s/health/heartRate/queryHeartRateDetailData"],
    "heart_rate_stat": ["v5/c2s/health/heartRate/pullStatVersionPageData"],
    "blood_oxygen":["v5/c2s/health/bloodOxygen/pullBloodOxygenDetailData"],
    "blood_oxygen_detail": ["v5/c2s/health/bloodOxygen/queryBloodOxygenDetailData"],
    "blood_oxygen_stat": ["v5/c2s/health/bloodOxygen/pullStatVersionPageData"],
    "blood_oxygen_warning": ["v5/c2s/health/bloodOxygen/queryBloodOxygenWarningDetailData"],
    "blood_oxygen_origin": ["v5/c2s/health/bloodOxygen/queryOriginData"],
    "blood_pressure": ["v5/c2s/health/bloodPressure/queryBloodPressureDetailData"],
    "blood_pressure_stat": ["v1/c2s/health/bloodPressure/queryBloodPressureStatData"],
    "blood_sugar": ["v5/c2s/health/glucose/queryGlucoseDetail"],
    "blood_sugar_stat": ["v5/c2s/health/glucose/pullStatVersionPageData"],
    "blood_sugar_warning": ["v5/c2s/health/glucose/queryGlucoseWarn"],
    "heart_rate_warning": ["v5/c2s/health/heartRate/queryHeartRateWarningDetailData"],
    "atrial_fibril": ["v5/c2s/health/atrialFibril/queryAtrialFibrilDetailData"],
    "atrial_fibril_warning": ["v5/c2s/health/atrialFibril/queryAtrialWarningDetailData"],
    "cardiovascular": ["v5/c2s/health/cardiovascular/queryCardiovascularRecordData"],
    "sedentary": ["v5/c2s/health/sedentary/querySedentaryDetailData"],
    "steps":       ["v5/c2s/sport/steps/pullStepsDetailData"],
    "steps_detail": ["v5/c2s/sport/steps/queryStepsDetailData"],
    "steps_stat": ["v1/c2s/sport/steps/pullStatVersionPageData"],
    "sleep":       ["v5/c2s/health/sleep/querySleepDayStatData"],
    "sleep_stat": ["v5/c2s/health/sleep/pullStatVersionPageData"],
    "sleep_status": ["v5/c2s/health/sleep/querySleepStatusData"],
    "sleep_index": ["v5/c2s/health/sleep/querySleepIndexStatData"],
    "sleep_rr": ["v5/c2s/health/sleep/querySleepRRIntervalDetailData"],
    "sleep_advice": ["v5/c2s/health/sleep/querySleepAdviceData"],
    "sleep_hr_stat": ["v1/c2s/health/sleep/querySleepHeartRateStatData"],
    "wrist_temperature_detail": ["v5/c2s/health/wrist/temperature/queryWristTemperatureDetailData"],
    "tumble":      ["v5/c2s/health/tumble/pullTumbleRecordData"],
    "app_usage":   ["v5/c2s/health/pullAppUsageStatPageList"],
    "app_usage_detail": ["v5/c2s/health/queryAppUsageDetailList"],
    "sport_goal": ["v2/c2s/sport/goal/queryUserGoal"],
    "insight":     ["v5/c2s/insight/queryRecentData"],
    "weight":      ["v1/c2s/health/weight/querySignedWeight"],
    "wrist_temperature": ["v5/c2s/health/wrist/temperature/pullStatVersionPageData"],
    "hrv": ["v5/c2s/health/heartRateVar/queryHeartRateVarDetailData"],
    "stress_detail": ["v5/c2s/health/stress/queryStressDetailData"],
    "stress_stat": ["v5/c2s/health/stress/pullStatVersionPageData"],
    "breath_rate": ["v5/c2s/health/breathRate/queryBreathRateDetailData"],
    "physical_mental_detail": ["v5/c2s/health/physical/mental/queryPhysicalMentalHealthDetailData"],
    "physical_mental_stat": ["v5/c2s/health/physical/mental/pullStatVersionPageData"],
    "physical_mental_achievement": ["v5/c2s/health/physical/mental/pullAchievementVersionPageData"],
    "hearing": ["v5/c2s/health/audition/queryAuditionRecordDetailData"],
    "hearing_stat": ["v2/c2s/health/audition/queryAuditionRecordStatData"],
    "cervical_stat": ["v5/c2s/health/cervical/queryCervicalStatData"],
    "cervical_action": ["v5/c2s/health/cervical/queryCervicalActionDetailData"],
    "sunshine": ["v5/c2s/health/sunshine/querySunshineDetailData"],
    "sunshine_stat": ["v5/c2s/health/sunshine/pullSunshineStatPageList"],
    "ecg": ["v3/c2s/health/cardiogram/queryCardiogramData"],
    "snore_osa_detail": ["v5/c2s/health/snore/queryOsaModelDetailData"],
    "snore_osa_sum": ["v5/c2s/health/snore/queryOsaModelSumData"],
    "snore_env_noise": ["v5/c2s/health/snore/querySnoreEnvNoiseDetailData"],
    "snore_feature": ["v5/c2s/health/snore/querySnoreFeatureDetailData"],
    "snore_stat": ["v5/c2s/health/snore/querySnoreStatData"],
    "sensor_osa": ["v5/c2s/health/SensorOSA/querySensorOSADetailData"],
    "exercise_intensity": ["v5/c2s/exercise/intensity/pullStatVersionPageData"],
    "weight_target": ["v5/c2s/health/weight/target/pullStatVersionPageData"],
    "vitamin": ["v5/c2s/health/vitamin/pullVitaminPageList"],
    "physiological_cycle": ["v5/c2s/health/physiological/pullPhysiologicalCycleData"],
    "physiological_symptoms": ["v5/c2s/health/physiological/pullPhysiologicalCycleSymptomsData"],
    "ovulation": ["v5/c2s/health/physiological/pullOvulationInfoPageList"],
    "sport_record": ["v3/c2s/sport/data/querySportRecordVersion"],
    "sport_file": ["v5/c2s/sport/data/queryFileSportRecordData"],
    "sport_stat": ["v3/c2s/sport/data/querySportStatData"],
}

METRIC_DATASETS = {
    "stress": ("stress_detail", "stress_stat"),
    "physical_mental": ("physical_mental_detail", "physical_mental_stat",
                        "physical_mental_achievement"),
}

MCP_METRIC_CHOICES = tuple(ENDPOINTS) + tuple(METRIC_DATASETS)
MetricName = Literal.__getitem__(MCP_METRIC_CHOICES)

VERSIONED_DETAILS = {
    "hrv": "v2/c2s/health/heartRateVar/queryHeartRateVarDetailVersion",
    "breath_rate": "v3/c2s/health/breathRate/queryBreathRateDetailVersion",
    "heart_rate_detail": "v3/c2s/health/heartRate/queryHeartRateDetailVersionList",
    "steps_detail": "v3/c2s/sport/steps/queryStepsDetailVersionList",
    "sleep_status": "v3/c2s/health/sleep/querySleepStatusVersionList",
    "sleep_rr": "v3/c2s/health/sleep/querySleepRRIntervalDetailVersion",
    "stress_detail": "v2/c2s/health/stress/queryStressDetailVersion",
    "physical_mental_detail": "v4/c2s/health/physical/mental/queryPhysicalMentalHealthDetailVersion",
    "blood_pressure": "v1/c2s/health/bloodPressure/queryBloodPressureDetailVersion",
    "blood_sugar": "v4/c2s/health/glucose/queryGlucoseDetailVersion",
    "blood_sugar_warning": "v4/c2s/health/glucose/queryGlucoseWarnVersion",
    "atrial_fibril": "v1/c2s/health/atrialFibril/queryAtrialFibrilDetailVersion",
    "atrial_fibril_warning": "v1/c2s/health/atrialFibril/queryAtrialWarningDetailVersion",
    "cardiovascular": "v3/c2s/health/cardiovascular/queryCardiovascularRecordVersion",
    "sedentary": "v1/c2s/health/sedentary/querySedentaryDetailVersion",
    "sleep_advice": "v3/c2s/health/sleep/querySleepAdviceVersion",
    "hearing": "v2/c2s/health/audition/queryAuditionRecordDetailVersion",
    "cervical_action": "v3/c2s/health/cervical/queryCervicalActionDetailVersion",
    "sunshine": "v5/c2s/health/sunshine/querySunshineDetailVersion",
    "heart_rate_warning": "v3/c2s/health/heartRate/queryHeartRateWarningDetailVersionList",
    "blood_oxygen_detail": "v3/c2s/health/bloodOxygen/queryBloodOxygenDetailVersionList",
    "blood_oxygen_warning": "v3/c2s/health/bloodOxygen/queryBloodOxygenWarningDetailVersion",
    "blood_oxygen_origin": "v3/c2s/health/bloodOxygen/queryOriginDataVersionList",
    "wrist_temperature_detail": "v4/c2s/health/wrist/temperature/queryWristTemperatureDetailVersion",
    "ecg": "v2/c2s/health/cardiogram/queryCardiogramDataVersion",
    "snore_osa_detail": "v3/c2s/health/snore/queryOsaModelDetailVersion",
    "snore_osa_sum": "v3/c2s/health/snore/queryOsaModelSumVersion",
    "snore_env_noise": "v3/c2s/health/snore/querySnoreEnvNoiseDetailVersion",
    "snore_feature": "v3/c2s/health/snore/querySnoreFeatureDetailVersion",
    "sensor_osa": "v3/c2s/health/SensorOSA/querySensorOSADetailVersion",
    "physiological_cycle": "v4/c2s/health/physiological/queryPhysiologicalCycleVersion",
    "physiological_symptoms": "v4/c2s/health/physiological/queryPhysiologicalCycleSymptomsVersion",
    "ovulation": "v5/c2s/health/physiological/queryOvulationInfoVersion",
}

VERSIONED_RECORDS = {
    "snore_stat": "v2/c2s/health/snore/querySnoreStatVersion",
    "sleep_index": "v3/c2s/health/sleep/querySleepIndexStatVersion",
    "sleep_hr_stat": "v3/c2s/health/sleep/querySleepHeartRateStatVersion",
    "blood_pressure_stat": "v1/c2s/health/bloodPressure/queryBloodPressureStatVersion",
    "hearing_stat": "v2/c2s/health/audition/queryAuditionRecordStatVersion",
    "cervical_stat": "v3/c2s/health/cervical/queryCervicalStatVersion",
}

VERSIONED_SINGLE = {**VERSIONED_DETAILS, **VERSIONED_RECORDS}

VERSIONED_STATS = {
    "heart_rate_stat": "v3/c2s/health/heartRate/queryHeartRateStatVersionList",
    "steps_stat": "v2/c2s/sport/steps/queryStepsStatVersionList",
    "sleep_stat": "v3/c2s/health/sleep/querySleepStatVersionList",
    "stress_stat": "v2/c2s/health/stress/queryStressStatVersion",
    "physical_mental_stat": "v4/c2s/health/physical/mental/queryPhysicalMentalHealthStatVersionList",
    "physical_mental_achievement": "v4/c2s/health/physical/mental/queryPhysicalMentalHealthAchievementVersionList",
    "blood_sugar_stat": "v4/c2s/health/glucose/queryGlucoseStatVersion",
    "blood_oxygen_stat": "v3/c2s/health/bloodOxygen/queryBloodOxygenStatVersionList",
    "sunshine_stat": "v5/c2s/health/sunshine/querySunshineStatVersion",
    "exercise_intensity": "v5/c2s/exercise/intensity/queryExerciseIntensityVersion",
    "weight_target": "v5/c2s/health/weight/target/queryWeightTargetVersion",
    "vitamin": "v5/c2s/health/vitamin/queryVitaminVersion",
}

VERSIONED_SPORT = {
    "sport_record": ("v3/c2s/sport/data/querySportRecordVersion", "modifiedTime"),
    "sport_file": ("v3/c2s/sport/data/querySportRecordVersion", "modifiedTime"),
    "sport_stat": ("v3/c2s/sport/data/querySportStatVersion", "modifiedTime"),
}

DETAIL_VERSION_FIELDS = {"steps_detail": "modifiedTime"}
DETAIL_VERSION_QUERY_FLAGS = {"stress_detail": 1, "physical_mental_detail": 1}

BEIJING = datetime.timezone(datetime.timedelta(hours=8), "Asia/Shanghai")

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
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"http_error": r.returncode, "body": "non_json_response"}

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
        payload = dict(it)
        payload.pop("__cacheKey", None)
        d = str(it.get("__cacheKey") or d)
        con.execute("INSERT OR REPLACE INTO cloud_data VALUES(?,?,?,?)",
                    (metric, d, json.dumps(payload), now))
        n += 1
    con.commit(); con.close()
    return n

def _api_ok(response):
    return response.get("errorCode") in (0, "0")

def _records(body):
    """Convert common cloud response shapes to top-level records without flattening nested dataList."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("dataList", "recordList", "resultList", "detailList", "list"):
            rows = body.get(key)
            if isinstance(rows, list):
                return rows
        return [body] if body else []
    return []

def _version_values(body):
    if isinstance(body, list):
        return [int(value) for value in body
                if isinstance(value, (int, float, str)) and str(value).isdigit()]
    if not isinstance(body, dict):
        return []
    values = body.get("modifiedTimestampList")
    if isinstance(values, list):
        return [int(value) for value in values if value is not None]
    values = body.get("modifiedTime")
    if isinstance(values, list):
        return [int(value) for value in values if value is not None]
    values = []
    for row in _records(body):
        if not isinstance(row, dict):
            continue
        value = row.get("modifiedTimestamp", row.get("modifiedTime"))
        if value is not None:
            values.append(int(value))
    return values

def _fetch_versioned_sport(metric, auth, days):
    if metric == "sport_file" and not auth.get("encrypt_key_enc"):
        return None, "encrypt_key_enc_required"
    version_endpoint, field = VERSIONED_SPORT[metric]
    values = []
    since = _first_day_timestamp(days)
    cursor = since
    for _ in range(100):
        response = _post(version_endpoint, {field: max(cursor, since), "queryFlag": 0}, auth)
        if not _api_ok(response):
            return None, response.get("errorCode")
        body = response.get("body") or {}
        page = _version_values(body)
        if not page:
            break
        values.extend(page)
        next_cursor = max(page)
        if next_cursor <= cursor or not isinstance(body, dict) or not body.get("hasMore"):
            break
        cursor = next_cursor
    else:
        return None, "pagination_limit"

    items = []
    for modified_time in sorted(set(values)):
        if metric == "sport_record":
            items.append({"modifiedTime": modified_time,
                          "source": "sport_record_version"})
            continue
        request = {field: modified_time}
        if metric == "sport_file":
            request["encryptKeyEnc"] = auth["encrypt_key_enc"]
        response = _post(ENDPOINTS[metric][0], request, auth)
        if not _api_ok(response):
            return None, response.get("errorCode")
        items.extend(_records(response.get("body")))
    return items, None

def _fetch_versions(path, auth, query_flag=None, since=0):
    values = []
    cursor = since
    for _ in range(100):
        request = {"modifiedTimestamp": cursor}
        if query_flag is not None:
            request["queryFlag"] = query_flag
        response = _post(path, request, auth)
        if not _api_ok(response):
            return None, response.get("errorCode")
        body = response.get("body") or {}
        page = _version_values(body)
        if not page:
            break
        values.extend(page)
        next_cursor = max(page)
        if next_cursor <= cursor or not isinstance(body, dict) or not body.get("hasMore"):
            break
        cursor = next_cursor
    else:
        return None, "pagination_limit"
    return sorted(set(values)), None

def _first_day_timestamp(days):
    today = datetime.datetime.now(BEIJING).date()
    first_day = today - datetime.timedelta(days=max(days, 1) - 1)
    return _beijing_day_window(first_day)[0]

def _fetch_versioned_details(metric, auth, days):
    versions, error = _fetch_versions(VERSIONED_SINGLE[metric], auth, query_flag=0,
                                      since=_first_day_timestamp(days))
    if error is not None:
        return None, error
    items = []
    detail_field = DETAIL_VERSION_FIELDS.get(metric, "modifiedTimestamp")
    for modified_ts in versions:
        request = {detail_field: modified_ts}
        query_flag = DETAIL_VERSION_QUERY_FLAGS.get(metric)
        if query_flag is not None:
            request["queryFlag"] = query_flag
        response = _post(ENDPOINTS[metric][0], request, auth)
        if not _api_ok(response):
            return None, response.get("errorCode")
        items.extend(_records(response.get("body")))
    return items, None

def _fetch_versioned_stats(metric, auth, days):
    versions, error = _fetch_versions(VERSIONED_STATS[metric], auth, query_flag=0,
                                      since=_first_day_timestamp(days))
    if error is not None:
        return None, error
    if not versions:
        return [], None

    items = []
    start = min(versions)
    end = max(versions)
    endpoint = ENDPOINTS[metric][0]
    zero_cursor = False
    for _ in range(100):
        if not zero_cursor and start > end:
            break
        request = {"queryFlag": 0, "startModifiedTimestamp": start,
                   "endModifiedTimestamp": 0 if zero_cursor else end}
        response = _post(endpoint, request, auth)
        if not _api_ok(response):
            if not zero_cursor:
                # Some stat APIs only accept the service's zero/zero page cursor.
                zero_cursor = True
                start = 0
                items.clear()
                continue
            return None, response.get("errorCode")
        body = response.get("body") or {}
        page = _records(body)
        items.extend(page)
        if not isinstance(body, dict) or not body.get("hasMore") or not page:
            break
        page_versions = [int(value) for row in page if isinstance(row, dict)
                         for value in [row.get("modifiedTimestamp", row.get("modifiedTime"))]
                         if value is not None]
        if not page_versions:
            break
        next_start = max(page_versions) + 1
        if next_start <= start:
            break
        start = next_start
    else:
        return None, "pagination_limit"
    return items, None

def _beijing_day_window(day):
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=BEIJING)
    end = start + datetime.timedelta(days=1) - datetime.timedelta(milliseconds=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

def _payload_date(item):
    for key in ("date", "dataCreatedTimestamp", "startTimestamp", "measurementTime",
                "timestamp", "modifiedTimestamp", "modifiedTime"):
        value = item.get(key)
        if value is None:
            continue
        if key == "date":
            value = str(value)
            if len(value) == 8 and value.isdigit():
                return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
            if len(value) == 10 and value[4] == "-":
                return value
        try:
            timestamp = int(value)
            if timestamp <= 0:
                continue
            if timestamp < 100000000000:
                timestamp *= 1000
            return datetime.datetime.fromtimestamp(timestamp / 1000, BEIJING).date().isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            continue
    return None

def _recent_items(items, days):
    today = datetime.datetime.now(BEIJING).date()
    first_day = today - datetime.timedelta(days=max(days, 1) - 1)
    result = []
    for item in items:
        day = _payload_date(item)
        if day is None or day >= first_day.isoformat():
            result.append(item)
    return result

def _embedded_metric_items(metric, outer_items):
    source_key, value_key = {
        "hrv": ("hrv", "heartRateVarValue"),
        "stress_detail": ("stress", "stressValue"),
    }[metric]
    result = []
    for outer_index, outer in enumerate(outer_items):
        if not isinstance(outer, dict):
            continue
        for index, point in enumerate(outer.get("dataList") or []):
            if not isinstance(point, dict):
                continue
            value = point.get(source_key)
            if value is None:
                continue
            row = {
                value_key: value,
                "startTimestamp": outer.get("startTimestamp"),
                "endTimestamp": outer.get("endTimestamp"),
                "modifiedTimestamp": outer.get("modifiedTimestamp"),
                "startTimeOffset": point.get("startTimeOffset"),
                "source": "physical_mental_detail",
            }
            if metric == "stress_detail":
                row.update({"stressState": point.get("stressState"),
                            "stressType": point.get("type"),
                            "display": point.get("display")})
            else:
                row["display"] = point.get("display")
            row["__cacheKey"] = (f"{metric}:{outer.get('startTimestamp')}:"
                                  f"{outer.get('modifiedTimestamp')}:{outer_index}:{index}")
            result.append(row)
    return result

def cloud_sync(metric: MetricName, days: int = 7) -> dict:
    """从云端拉取指定指标, 写入本地缓存.
    pull端点限制单次范围≤1天(23103), 内部按天循环.
    sleep: version游标全量(单条1请求, 仅增量ts); app_usage: date+queryFlag; weight: userTagId+pageSize."""
    if metric in METRIC_DATASETS:
        results = [cloud_sync(dataset, days) for dataset in METRIC_DATASETS[metric]]
        errors = [result for result in results if result.get("error")]
        result = {"metric": metric, "datasets": results}
        if errors:
            result["errors"] = errors
        return result

    auth = _load_auth()
    eps = ENDPOINTS.get(metric)
    if not eps:
        return {"error": f"unknown metric {metric}, 可用: {list(ENDPOINTS)}"}
    ep = eps[0]
    items = []
    derived_from = None
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
    elif metric in VERSIONED_SINGLE:
        items, error = _fetch_versioned_details(metric, auth, days)
        if error is not None:
            return {"error": f"{metric} detail query failed", "errorCode": error}
        items = _recent_items(items, days)
        if metric == "hrv" and not items:
            source_items, error = _fetch_versioned_details("physical_mental_detail", auth, days)
            if error is None:
                source_items = _recent_items(source_items, days)
                _cache("physical_mental_detail", source_items)
                items = _embedded_metric_items("hrv", source_items)
                if items:
                    derived_from = "physical_mental_detail"
        if metric == "stress_detail" and not items:
            source_items, error = _fetch_versioned_details("physical_mental_detail", auth, days)
            if error is None:
                source_items = _recent_items(source_items, days)
                _cache("physical_mental_detail", source_items)
                items = _embedded_metric_items("stress_detail", source_items)
                if items:
                    derived_from = "physical_mental_detail"
    elif metric in VERSIONED_STATS:
        items, error = _fetch_versioned_stats(metric, auth, days)
        if error is not None:
            return {"error": f"{metric} statistics query failed", "errorCode": error}
        items = _recent_items(items, days)
    elif metric in VERSIONED_SPORT:
        items, error = _fetch_versioned_sport(metric, auth, days)
        if error is not None:
            if error == "encrypt_key_enc_required":
                return {"metric": metric,
                        "error": "encrypted sport file requires an app-generated encryptKeyEnc",
                        "errorCode": error}
            return {"error": f"{metric} version query failed", "errorCode": error}
        items = _recent_items(items, days)
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
    elif metric == "app_usage_detail":
        today = datetime.datetime.now(BEIJING).date()
        for back in range(max(days, 1)):
            day = today - datetime.timedelta(days=back)
            date = int(day.strftime("%Y%m%d"))
            r = _post(ep, {"startDate": date, "endDate": date}, auth)
            if r.get("errorCode") != 0:
                return {"error": "app usage detail query failed",
                        "errorCode": r.get("errorCode"),
                        "httpError": r.get("http_error")}
            items.extend(_records(r.get("body")))
    elif metric == "sport_goal":
        r = _post(ep, {}, auth)
        if r.get("errorCode") == 0:
            items.extend(_records(r.get("body")))
        else:
            return {"error": "sport goal query failed",
                    "errorCode": r.get("errorCode"),
                    "httpError": r.get("http_error")}
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
                return {"error": f"day {d} failed", "errorCode": r.get("errorCode"),
                        "httpError": r.get("http_error")}
    n = _cache(metric, items)
    if metric == "wrist_temperature" or metric in {
            "hrv", "stress_detail", "stress_stat", "breath_rate",
            "physical_mental_detail", "physical_mental_stat", "physical_mental_achievement",
            "blood_pressure", "blood_sugar", "atrial_fibril", "atrial_fibril_warning",
            "cardiovascular", "sedentary", "sleep_advice", "sleep_hr_stat", "hearing",
            "cervical_stat", "cervical_action", "sunshine",
            "app_usage_detail", "sport_goal",
            *VERSIONED_SINGLE, *VERSIONED_STATS, *VERSIONED_SPORT}:
        dates = sorted({day for item in items if (day := _payload_date(item)) is not None})
        result = {"metric": metric, "endpoint": ep, "rows_cached": n, "dates": dates}
        if derived_from:
            result["derived_from"] = derived_from
        return result
    return {"metric": metric, "endpoint": ep, "rows_cached": n,
            "raw_sample": items[:2]}

def cloud_query(metric: MetricName, date: str = None) -> dict:
    """查询本地缓存 (先 sync 再 query). date=YYYYMMDD 可选."""
    if metric in METRIC_DATASETS:
        datasets = {name: cloud_query(name, date)
                    for name in METRIC_DATASETS[metric]}
        return {"metric": metric,
                "count": sum(dataset["count"] for dataset in datasets.values()),
                "datasets": datasets}

    con = _db()
    if date:
        requested = date.replace("-", "")
        requested_iso = (f"{requested[:4]}-{requested[4:6]}-{requested[6:8]}"
                         if len(requested) == 8 and requested.isdigit() else requested)
        rows = con.execute("SELECT date, payload FROM cloud_data WHERE metric=?",
                           (metric,)).fetchall()
        data = []
        for cached_date, payload in rows:
            item = json.loads(payload)
            if (str(cached_date).replace("-", "") == requested
                    or _payload_date(item) == requested_iso):
                data.append(item)
    else:
        rows = con.execute("SELECT date, payload FROM cloud_data WHERE metric=? ORDER BY date DESC LIMIT 100",
                           (metric,)).fetchall()
        data = [json.loads(r[1]) for r in rows]
    con.close()
    return {"metric": metric, "count": len(data), "data": data}

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

def register_tools(server):
    """Register MCP tools with accurate read/write annotations."""
    from mcp.types import ToolAnnotations

    server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))(cloud_sync)
    server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(cloud_query)
    server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(cloud_analyze)
    server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(cloud_status)

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
    register_tools(mcp)
    mcp.run()
