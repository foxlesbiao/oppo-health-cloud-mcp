#!/usr/bin/env python3
"""OPPO Health account login via SMS and optional secondary ID verification."""

import argparse
import base64
import getpass
import gzip
import hashlib
import hmac
import json
import os
import secrets
import string
import subprocess
import sys
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA1
from Crypto.PublicKey import RSA
from Crypto.Util import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.abspath(
    os.environ.get("OPPO_HEALTH_AUTH_FILE") or os.path.join(HERE, "auth.json")
)

UC_HOST = "https://uc-client-cn.heytapmobi.com"
VERIFY_HOST = "https://uc-client-cn.heytapmobi.com"

BIZ_APP_ID = "30129205"
BIZ_APP_KEY = "07f7a77f28c14f70ac927d1dcfac85b3"
ACCOUNT_APP_ID = "31288517"
ACCOUNT_PACKAGE = "com.oplus.account.open.sdk"
ACCOUNT_PACKAGE_SIGN = "00e7ec6745698936072925f64fc2a3e8"
HEALTH_PACKAGE = "com.heytap.health"
HEALTH_VERSION_CODE = "6093700"
HEALTH_VERSION_NAME = "6.9.37_a7d98c1_260920"

RSA_PUB_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDpgSW5VkZ6/xvh+wMXezrOokNdiupu"
    "vuMj4RVJy44byWDupl4H37z907A26RVdFzMeyLUQB4rsDIaXdxCODlljWW+/K96uF5"
    "MsDtOFUBw7VlOclIjcYTv/YDQEul8JoXoOuy1Yf3b5sbTpTuVTcl97tAuLJ8PoGe2K"
    "7N3B1eUQqQIDAQAB"
)
APP_KEY = "3cd48b0c781835478b0a1783a9eff0c9"
APP_SECRET = "dc94930b84c43e7696af9bf14bc45b65"
IDENTITY_SIGN_KEY = "4iAEb620alQ8s8c8ss8o0K8sS"
IDENTITY_SIGN_SECRET = "80620774fE983aab1E8C564e3f213b62"
MOBILE_CODE_LOGIN_SCENE = "99m1eE15MAUPz7pEtMUw"

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 15; V2245A Build/V417IR; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 "
    "Safari/537.36 DayNight/1 ColorOSVersion/ language/zh "
    "AcLanguageTag/zh-Hans-CN AcLegacyLanguageTag/zh-CN locale/zh_CN_#Hans "
    "timeZone/Asia/Shanghai model/V2245A appPackageName/com.heytap.health "
    "appVersion/6093700 foldMode/ largeScreen/false displayWidth/1600 "
    "displayHeight/864 realScreenWidth/1600 realScreenHeight/900 navHeight/72 "
    "isThird/1 X-BusinessSystem/heytap hardwareType/Mobile isMagicWindow/0 "
    "JSBridge/2 ClientType/UserCenter usercenter/6.9.37_a7d98c1_260920_ "
    "WebFitMethod/1 switchHost/1 localstorageEncrypt/1 isTalkBackState/0 "
    "deepThemeColor/rgba(26,140,255,1.0) themeColor/rgba(26,140,255,1.0) "
    "themeTextColor/rgba(26,140,255,1.0) isPanel/0 regionCode/CN "
    "Business/account SystemCountryCode/ AcLegacyLanguageTag/zh-Hans-CN "
    "AcLanguageTag/zh deviceType/ANDROID;kyc/h5face;kyc/2.0"
)

_ALPHABET = string.ascii_letters + string.digits
_RSA_KEY = RSA.import_key(base64.b64decode(RSA_PUB_B64))


def _random_text(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _aes_ctr(key: bytes, iv: bytes, data: bytes) -> bytes:
    counter = Counter.new(128, initial_value=int.from_bytes(iv, "big"))
    return AES.new(key, AES.MODE_CTR, counter=counter).encrypt(data)


def _make_envelope(plain: str, key_size: int = 16) -> tuple[str, bytes, bytes]:
    key = _random_text(key_size).encode()
    iv = _random_text(16).encode()
    encrypted = _aes_ctr(key, iv, plain.encode())
    rsa = PKCS1_OAEP.new(_RSA_KEY, hashAlgo=SHA1)
    return ".".join((
        base64.b64encode(rsa.encrypt(key)).decode(),
        base64.b64encode(rsa.encrypt(iv)).decode(),
        base64.b64encode(encrypted).decode(),
    )), key, iv


def _open_envelope(envelope: str, key: bytes, iv: bytes) -> Any:
    encrypted = envelope.split(".")[-1]
    plain = _aes_ctr(key, iv, base64.b64decode(encrypted))
    return json.loads(plain)


def _trace(kind: str) -> str:
    return f"{BIZ_APP_ID}_{kind}_{int(time.time() * 1000)}_{_random_text(8)}"


def _sign_body(plain_body: str, sign_key: str, sign_secret: str) -> tuple[str, str]:
    request_time = str(int(time.time() * 1000))
    body_md5 = hashlib.md5(plain_body.encode()).hexdigest()
    canonical = (
        f"requestBody={body_md5}&requestTime={request_time}"
        f"&signAlgorithm=HMAC1_SK{sign_key}"
    )
    signature = base64.b64encode(
        hmac.new(sign_secret.encode(), canonical.encode(), hashlib.sha1).digest()
    ).decode()
    return signature, request_time


def _risk_env_param() -> str:
    payload = {
        "SysInfo": {
            "osVersion": "V417IR",
            "romVersion": "V417IR",
            "apiVersion": 35,
            "secVersion": "2025-06-01",
            "bootloaderVersion": "unknown",
            "usbStatus": False,
            "curTime": int(time.time() * 1000),
            "upTime": int(time.monotonic() * 1000),
            "activeTime": int(time.monotonic() * 1000),
        },
        "DevInfo": {
            "buildID": "",
            "model": "V2245A",
            "product": "V2245A",
            "brand": "heytap",
            "hwName": "mt6985",
            "platform": "phone",
        },
        "NetInfo": {
            "networkType": "WIFI",
            "cellIP": "",
            "isVpn": False,
            "vpnIP": "",
        },
        "EnvInfo": {
            "isRoot": False,
            "isVirtual": False,
            "vmApp": "",
            "hookFrame": False,
            "hookMethods": False,
            "isFileExist": False,
            "OSisDebuggable": False,
            "roSecure": 1,
        },
        "HardInfo": {
            "screenSize": "1600,900",
            "screenDpi": 320,
            "cpuID": "",
            "cpuType": "arm64-v8a,armeabi-v7a,armeabi",
            "btName": "NOP",
            "btMac": None,
        },
        "OtherInfo": {
            "batteryStatus": "discharging",
            "batteryPresent": True,
            "batteryHealth": 2,
            "sdkVersion": "1.1.0",
        },
    }
    return quote(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), safe="")


def _device_duid(device_id: str | None) -> str:
    if device_id and len(device_id) == 32 and all(c in string.hexdigits for c in device_id):
        suffix = device_id.lower()
    else:
        suffix = (
            hashlib.sha256(device_id.encode()).hexdigest()[:32]
            if device_id
            else "0" * 32
        )
    return f"{HEALTH_PACKAGE}{suffix}"


def _device_id_from_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _sdk_headers(plain_body: str, kind: str, native: bool = False) -> dict[str, str]:
    sign_key = APP_KEY if native else IDENTITY_SIGN_KEY
    sign_secret = APP_SECRET if native else IDENTITY_SIGN_SECRET
    signature, request_time = _sign_body(plain_body, sign_key, sign_secret)
    headers = {
        "content-type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN",
        "origin": "https://muc.heytap.com",
        "referer": "https://muc.heytap.com/",
        "user-agent": USER_AGENT,
        "x-app-acpackage": ACCOUNT_PACKAGE,
        "x-app-acversion": "30100" if native else "3.1.0",
        "x-app-hostpackage": HEALTH_PACKAGE,
        "x-app-hostversion": HEALTH_VERSION_CODE,
        "x-biz-appid": BIZ_APP_ID,
        "x-biz-appkey": BIZ_APP_KEY,
        "x-biz-package": HEALTH_PACKAGE,
        "x-biz-version": HEALTH_VERSION_CODE,
        "x-context-country": "CN",
        "x-context-locale": "zh_CN_#Hans",
        "x-context-maskregion": "CN",
        "x-context-timezone": "Asia/Shanghai",
        "x-device-brand": "heytap",
        "x-device-clienttype": "ANDROIDSDK",
        "x-device-hardwaretype": "Mobile",
        "x-device-model": "V2245A",
        "x-app-overseaclient": "false",
        "x-envelope-version": "V1",
        "x-app-acappkey": APP_KEY,
        "x-sign-key": sign_key,
        "x-sign-algorithm": "HMAC1_SK",
        "x-requesttime": request_time,
        "x-sign": signature,
        "x-sdk-type": "open",
        "x-sdk-version": "30100" if native else "3.1.0",
        "x-sys-androidversion": "35",
        "x-sys-romversion": "",
        "x-sys-osversion": "15",
        "x-sys-osversioncode": "0",
        "x-sys-talkbackstate": "false",
        "x-app-traceid": _trace(kind),
        "x-biz-traceid": _trace(kind),
    }
    if native:
        headers["x-biz-version-code"] = HEALTH_VERSION_CODE
    return headers


def _sdk_post(
    session: requests.Session,
    url: str,
    body_obj: Any,
    kind: str,
    native: bool = False,
    extra_headers: dict[str, str] | None = None,
    compress_body: bool = False,
) -> Any:
    plain = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
    envelope, key, iv = _make_envelope(plain, 32 if native else 16)
    headers = _sdk_headers(plain, kind, native)
    if compress_body:
        headers["content-encoding"] = "gzip"
    if extra_headers:
        headers.update(extra_headers)
    payload = gzip.compress(envelope.encode()) if compress_body else envelope.encode()
    for _ in range(2):
        response = session.post(url, data=payload, headers=headers, timeout=20)
        if response.status_code == 222:
            continue
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} {response.reason}")
        return _open_envelope(response.text, key, iv)
    raise RuntimeError("public key refresh loop did not succeed")


def _assert_ok(result: dict[str, Any], step: str) -> dict[str, Any]:
    code = result.get("code")
    if code == 200 and result.get("data") is not None:
        return result["data"]
    error = result.get("error") or {}
    raise RuntimeError(f"{step} failed: code={code}, message={error.get('message', 'unknown')}")


def _find_account_token(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("xToken", "token", "accessToken", "idToken", "primaryToken"):
            token = value.get(key)
            if isinstance(token, str) and token:
                return token
        for item in value.values():
            token = _find_account_token(item)
            if token:
                return token
    elif isinstance(value, list):
        for item in value:
            token = _find_account_token(item)
            if token:
                return token
    return None


class AccountLoginSession:
    def __init__(self, device_id: str | None = None, sdk_device_id: str | None = None):
        self.sdk_device_id = sdk_device_id
        self.session = requests.Session()
        self.session.headers.update({
            "x-requested-with": HEALTH_PACKAGE,
            "x-sys-duid": _device_duid(sdk_device_id or device_id),
        })
        self.process_token = ""
        self.ticket = ""
        self.device_id = device_id or ""
        self.account_login_data: dict[str, Any] = {}

    def config(self) -> dict[str, Any]:
        data = _assert_ok(
            _sdk_post(self.session, f"{UC_HOST}/identity/sdk/v1/config/login", {}, "config"),
            "login config",
        )
        return {
            "main": data.get("mainValidationConfig"),
            "second": data.get("secondValidationConfigs"),
        }

    def check(self, phone: str, country_calling_code: str = "+86") -> None:
        body = {
            "accountId": phone,
            "countryCallingCode": country_calling_code,
            "sceneId": MOBILE_CODE_LOGIN_SCENE,
            "fromRegisterPage": False,
            "deviceToken": "{}",
            "captchaCode": "",
            "captchaAppId": None,
        }
        data = _assert_ok(
            _sdk_post(
                self.session,
                f"{UC_HOST}/identity/v1/authn/check",
                body,
                "check",
                extra_headers={"X-Validation-Method": "phone", "X-Validation-Type": "verificationCode"},
            ),
            "account check",
        )
        self.process_token = str(data.get("processToken") or "")
        if not self.process_token:
            raise RuntimeError("account check did not return processToken")

    def send_code(self) -> None:
        body = {"captchaType": "SMS", "captchaCode": "", "captchaAppId": None}
        _assert_ok(
            _sdk_post(
                self.session,
                f"{UC_HOST}/identity/v1/authn/send-verification-code",
                {**body, "processToken": self.process_token},
                "send-code",
            ),
            "send verification code",
        )

    def validate_code(self, code: str) -> None:
        data = _assert_ok(
            _sdk_post(
                self.session,
                f"{UC_HOST}/identity/v1/authn/validate",
                {"validateParam": {"verificationCode": code}, "processToken": self.process_token},
                "validate",
                extra_headers={"X-Validation-Method": "phone", "X-Validation-Type": "verificationCode"},
            ),
            "verification code validation",
        )
        self.ticket = str(data.get("ticket") or "")
        if data.get("verificationUrl"):
            self._verify_engine(data["verificationUrl"])
        if not self.ticket:
            raise RuntimeError("validation did not return ticket")

    def _verify_engine(self, verification_url: str) -> None:
        query = parse_qs(urlparse(verification_url).query)
        process_token = (query.get("processToken") or [self.process_token])[0]
        scene_id = (query.get("sceneId") or [MOBILE_CODE_LOGIN_SCENE])[0]
        env_info = json.dumps(
            {
                "sceneId": scene_id,
                "thirdPartyAppInfo": "",
                "enableFinger": False,
                "enablePin": False,
            },
            separators=(",", ":"),
        )
        _assert_ok(
            _sdk_post(
                self.session,
                f"{VERIFY_HOST}/api/verification/check",
                {
                    "envInfo": env_info,
                    "processToken": process_token,
                    "captchaCode": "",
                    "deviceToken": {
                        "X-Safety-DeviceName": quote("V2245A", safe=""),
                        "X-Safety-MarketName": quote("V2245A", safe=""),
                    },
                },
                "verify-check",
            ),
            "secondary verification check",
        )
        list_result = _sdk_post(
            self.session,
            f"{VERIFY_HOST}/api/verification/list",
            {"processToken": process_token},
            "verify-list",
        )
        methods = (list_result.get("data") or {}).get("verMethodList") or []
        if not methods:
            raise RuntimeError("secondary verification list is empty")
        selected = next((item for item in methods if item.get("verMethod") == "SUFFIX_ID_NUMBER"), methods[0])
        method = selected.get("verMethod")
        if method != "SUFFIX_ID_NUMBER":
            raise RuntimeError(f"unsupported secondary verification method: {method}")
        suffix = getpass.getpass("ID number last 6 chars: ")
        result = _sdk_post(
            self.session,
            f"{VERIFY_HOST}/api/verification/validate-data",
            {"verMethod": method, "validateData": suffix, "processToken": process_token},
            "verify-validate",
        )
        data = _assert_ok(result, "secondary verification")
        ticket = data.get("ticket")
        if not ticket:
            raise RuntimeError("secondary verification did not return ticket")
        self.ticket = str(ticket)
        judge_result = _sdk_post(
            self.session,
            f"{VERIFY_HOST}/completion/v1/redirect-judge",
            {
                "processToken": process_token,
                "reRegister": False,
                "ticket": self.ticket,
            },
            "redirect-judge",
        )
        judge_data = _assert_ok(judge_result, "redirect judge")
        if judge_data.get("completionUrl"):
            raise RuntimeError("redirect judge requested an additional completion page")

    def login(self) -> str:
        body = {
            "packages": [HEALTH_PACKAGE],
            "processToken": self.process_token,
            "ticket": self.ticket,
        }
        result = _sdk_post(self.session, f"{UC_HOST}/identity/v1/authn/login", body, "login")
        data = _assert_ok(result, "account login")
        self.account_login_data = data
        device_id = data.get("deviceId")
        if isinstance(device_id, str) and device_id:
            self.device_id = device_id
        token = _find_account_token(data)
        if not token:
            raise RuntimeError("account login succeeded but no account token was returned")
        return token

    def authorize_health_token(self, account_token: str) -> dict[str, Any]:
        account_token_data = self.account_login_data.get("accountToken") or {}
        env_info = json.dumps(
            {
                "appId": ACCOUNT_APP_ID,
                "deviceId": self.device_id,
                "envParam": _risk_env_param(),
                "pkgName": ACCOUNT_PACKAGE,
                "pkgNameSign": ACCOUNT_PACKAGE_SIGN,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        data = _assert_ok(
            _sdk_post(
                self.session,
                f"{UC_HOST}/authorization/v1/token/authorize",
                {"envInfo": env_info},
                "authorize",
                native=True,
                extra_headers={
                    "x-token": account_token,
                    "x-acidtoken": account_token_data.get("idToken") or "",
                    "x-app-deviceid": self.device_id,
                    "x-sys-duid": _device_duid(self.sdk_device_id or self.device_id),
                    "user-agent": "okhttp/4.9.3.7",
                    "x-biz-version": HEALTH_VERSION_NAME,
                    "x-device-ht": "900",
                    "x-device-wd": "1600",
                    "x-device-lsd": "false",
                    "x-sys-osbuildtime": "1791966484000",
                    "x-sys-rpname": "PD2245",
                    "x-sys-rotaver": "",
                    "x-app-foldmode": "",
                    "x-safety-devicename": "",
                    "x-safety-marketname": "",
                },
                compress_body=True,
            ),
            "health token authorize",
        )
        biz_token = data.get("v3BizTokenResp") or {}
        if not biz_token.get("accessToken"):
            raise RuntimeError("token authorize response did not contain health accessToken")
        return {
            "token": biz_token["accessToken"],
            "token_auth_id": data.get("deviceId") or self.device_id,
            "refresh_token": biz_token.get("refreshToken") or "",
            "access_token_exp": biz_token.get("accessTokenExp") or 0,
            "refresh_token_exp": biz_token.get("refreshTokenExp") or 0,
        }


def _health_login(token: str, token_auth_id: str) -> str:
    from cloud_mcp import (APPID, APP_KEY_VERSION, APP_PACKAGE, APP_VERSION,
                           _new_nonce, _new_ts, _sign)

    body = json.dumps({"appPackage": HEALTH_PACKAGE, "token": token}, separators=(",", ":"))
    headers = {
        "appid": APPID,
        "app-package": APP_PACKAGE,
        "app-version": APP_VERSION,
        "nonce": _new_nonce(),
        "timestamp": _new_ts(),
        "token": token,
        "token-auth-id": token_auth_id,
    }
    signature = _sign(headers, body)
    header_pairs = [
        ("Content-Type", "application/json; charset=UTF-8"),
        ("User-Agent", "okhttp/4.9.3.7"),
        ("app-key-version", APP_KEY_VERSION),
        ("app-package", APP_PACKAGE),
        ("appid", APPID),
        ("app-version", APP_VERSION),
        ("versionName", HEALTH_VERSION_NAME),
        ("lang", "zh-CN"),
        ("os-type", "1"),
        ("risk-sign", "2"),
    ]
    header_pairs.extend(headers.items())
    header_pairs.append(("signature", signature))
    command = [
        "curl", "-s", "-m", "20", "-X", "POST",
        "https://sport.health.heytapmobi.com/sporthealth/v1/c2s/account/login",
        "--data-binary", body,
    ]
    for name, value in header_pairs:
        command.extend(("-H", f"{name}: {value}"))
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    payload = json.loads(result.stdout)
    if payload.get("errorCode") not in (0, "0"):
        message = payload.get("message") or payload.get("errorMsg") or "unknown"
        raise RuntimeError(f"health login failed: code={payload.get('errorCode')}, message={message}")
    ssoid = (payload.get("body") or {}).get("ssoid")
    if not ssoid:
        raise RuntimeError("health login did not return ssoid")
    return str(ssoid)


def _write_auth(auth: dict[str, Any]) -> None:
    existing = {}
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, encoding="utf-8") as handle:
            existing = json.load(handle)
    existing.update(auth)
    temporary = AUTH_FILE + ".tmp"
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, AUTH_FILE)


def _load_auth() -> dict[str, Any]:
    if not os.path.exists(AUTH_FILE):
        return {}
    with open(AUTH_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def run_login(device_id: str | None = None, sdk_device_id: str | None = None) -> None:
    device_id = device_id or _device_id_from_env("OPPO_HEALTH_DEVICE_ID") or secrets.token_hex(16)
    sdk_device_id = (
        sdk_device_id
        or _device_id_from_env("OPPO_HEALTH_SDK_DEVICE_ID")
        or device_id
    )
    parent = os.path.dirname(AUTH_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _write_auth({"sdk_device_id": sdk_device_id})
    sdk = AccountLoginSession(
        device_id,
        sdk_device_id,
    )
    phone = getpass.getpass("Phone number: ").strip()
    country = input("Country calling code [+86]: ").strip() or "+86"
    sdk.check(phone, country)
    sdk.send_code()
    code = getpass.getpass("SMS verification code: ").strip()
    sdk.validate_code(code)
    account_token = sdk.login()
    health = sdk.authorize_health_token(account_token)
    token_auth_id = health["token_auth_id"]
    if not token_auth_id:
        raise RuntimeError("no token-auth-id/device-id available")
    ssoid = _health_login(health["token"], token_auth_id)
    _write_auth({
        "token": health["token"],
        "token_auth_id": token_auth_id,
        "ssoid": ssoid,
        "access_token_exp": health["access_token_exp"],
        "sdk_device_id": sdk_device_id,
    })
    print("Login complete; auth.json updated.")


def main() -> int:
    parser = argparse.ArgumentParser(description="OPPO Health account login")
    parser.add_argument("command", choices=["config", "login"])
    parser.add_argument("--device-id", help="OpenSDK deviceId; defaults to a random per-login ID")
    parser.add_argument(
        "--sdk-device-id",
        help="DUID source ID; defaults to --device-id or OPPO_HEALTH_SDK_DEVICE_ID",
    )
    args = parser.parse_args()
    try:
        if args.command == "config":
            session = AccountLoginSession(args.device_id or _load_auth().get("token_auth_id") or "")
            print(json.dumps(session.config(), ensure_ascii=False, separators=(",", ":")))
        else:
            run_login(args.device_id, args.sdk_device_id)
        return 0
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
