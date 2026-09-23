#!/usr/bin/env python3
"""OPPO 健康 API 签名复刻（pk9/HttpSignatureUtil 逆向结果，2026-09-18 50/50 对拍验证通过）

签名协议:
  canonical = sorted(k=v&)[:-1] + body.replaceAll(\\s*,)   # GET/空body 时无 body 尾巴
  fields: appid, app-package, nonce, timestamp, token, token-auth-id,
          app-version, os-type=1, lang=zh-CN, risk-sign=2
  signature = base64(HmacSHA256(httpSecret, canonical))

httpSecret = XXTEA-decrypt(BuildConfig.httpSecret, koa.a(DYNAMIC_KEY, STATIC_KEY))
  BuildConfig.httpSecret = "BKQyb7r9VBOiFVGONfdoaFhuyDkRgxLxN7L46w=="
  koa.a = 两个 UUID 逐字符交错
"""
import base64, struct, hmac, hashlib

DELTA = 0x9E3779B9
DYNAMIC_KEY = "e4f5d127-d57d-4d97-a1e7-e762a13f8793"
STATIC_KEY  = "a2a9725d-fb95-be34-160ad21378a1"
HTTP_SECRET_ENC = "BKQyb7r9VBOiFVGONfdoaFhuyDkRgxLxN7L46w=="

def _h(b, include_len=False):
    n = (len(b)+3)//4
    v = [0]*(n+1) if include_len else [0]*n
    if include_len: v[n] = len(b)
    for i,ch in enumerate(b): v[i>>2] |= ch << ((i&3)<<3)
    return v

def _g(v, has_len):
    ln = v[-1] if has_len else len(v)*4
    n = len(v)-1 if has_len else len(v)
    return bytes(((v[i>>2] >> ((i&3)<<3)) & 0xFF) for i in range(min(ln, n*4)))

def _mx(i,i2,i3,i4,i5,k):
    return ((i^i2) + (k[(i4&3)^i5]^i3)) ^ (((i3>>5)^(i2<<2)) + ((i2>>3)^(i3<<4)))

def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    v = _h(data); k = _h(key[:16].ljust(16, b' '))
    n = len(v)-1
    s = (((52//(n+1))+6)*DELTA) & 0xFFFFFFFF
    while s:
        e=(s>>2)&3; p=n; i4=v[0]
        while p>0:
            i4=(v[p]-_mx(s,i4,v[p-1],p,e,k))&0xFFFFFFFF; v[p]=i4; p-=1
        i4=(v[0]-_mx(s,i4,v[n],0,e,k))&0xFFFFFFFF; v[0]=i4
        s=(s-DELTA)&0xFFFFFFFF
    return _g(v, True)

def derive_http_secret() -> bytes:
    key = ''.join(a+b for a,b in zip(DYNAMIC_KEY, STATIC_KEY))
    out = xxtea_decrypt(base64.b64decode(HTTP_SECRET_ENC), key.encode())
    # 明文本身就是 base64 字符串, HMAC 直接用这串字符的 bytes
    return out

def sign_headers(headers: dict, body: str = "") -> str:
    """headers 需含: appid/app-package/nonce/timestamp/token/token-auth-id/app-version"""
    m = {
      'appid': headers['appid'],
      'app-package': headers['app-package'],
      'nonce': headers['nonce'],
      'timestamp': headers['timestamp'],
      'token': headers['token'],
      'token-auth-id': headers['token-auth-id'],
      'app-version': headers['app-version'],
      'os-type': '1',
      'lang': 'zh-CN',
      'risk-sign': '2',
    }
    canonical = ''.join(f'{k}={v}&' for k,v in sorted(m.items()))[:-1]
    if body:
        canonical += body.replace(' ','').replace('\n','').replace('\r','')
    return base64.b64encode(hmac.new(derive_http_secret(), canonical.encode(), hashlib.sha256).digest()).decode()

if __name__ == '__main__':
    import json, os
    samples = json.load(open(os.path.expanduser('~/oppo/oppo-health/cloud-mcp/sign_samples.json')))
    ok = sum(1 for s in samples if sign_headers(s['headers'], s.get('body','')) == s['signature'])
    print(f'对拍验证: {ok}/{len(samples)}')
    assert ok == len(samples), '签名复刻失败'
    print('PASS')
