"""한국투자증권 실전 서버의 청약 일정과 국내주식 시세 조회."""

import hashlib
import json
import os
import tempfile
import time
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from threading import Lock

import httpx


BASE_URL = "https://openapi.koreainvestment.com:9443"
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "kis"


class KisError(RuntimeError):
    pass


class KisClient:
    def __init__(self):
        self.key = os.environ.get("KIS_APP_KEY")
        self.secret = os.environ.get("KIS_APP_SECRET")
        if not self.key or not self.secret:
            raise KisError("KIS_APP_KEY와 KIS_APP_SECRET 설정이 필요합니다.")
        self.http = httpx.Client(base_url=BASE_URL, timeout=20)
        self.lock = Lock()
        self.last_call = 0.0
        key_id = hashlib.sha256(self.key.encode()).hexdigest()[:20]
        self.token_file = CACHE_DIR / f"{key_id}.json"

    def _token(self):
        if self.token_file.exists():
            try:
                saved = json.loads(self.token_file.read_text())
                if saved["expires_at"] > time.time() + 60:
                    return saved["token"]
            except (KeyError, ValueError, TypeError):
                pass
        res = self.http.post("/oauth2/tokenP", json={
            "grant_type": "client_credentials", "appkey": self.key, "appsecret": self.secret,
        })
        if res.is_error:
            raise KisError(f"KIS 토큰 발급 실패 (HTTP {res.status_code})")
        data = res.json()
        token = data.get("access_token")
        if not token:
            raise KisError("KIS 접근토큰을 발급받지 못했습니다.")
        CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=CACHE_DIR, delete=False) as out:
            json.dump({"token": token, "expires_at": time.time() + int(data["expires_in"])}, out)
        os.replace(out.name, self.token_file)
        return token

    def get(self, path, tr_id, params, continuation=""):
        with self.lock:
            try:
                for attempt in range(3):
                    token = self._token()
                    time.sleep(max(0, 0.55 - (time.monotonic() - self.last_call)))
                    self.last_call = time.monotonic()
                    res = self.http.get(path, params=params, headers={
                        "authorization": f"Bearer {token}", "appkey": self.key,
                        "appsecret": self.secret, "tr_id": tr_id, "custtype": "P",
                        "tr_cont": continuation,
                    })
                    data = res.json()
                    if res.is_success and data.get("rt_cd") == "0":
                        return data, res.headers.get("tr_cont", "")
                    code = data.get("msg_cd", str(res.status_code))
                    if attempt == 0 and code == "EGW00123":
                        self.token_file.unlink(missing_ok=True)
                        continue
                    if attempt < 2 and (res.status_code >= 500 or res.status_code == 429 or code == "EGW00201"):
                        time.sleep(2 ** attempt)
                        continue
                    raise KisError(f"KIS 조회 실패 ({tr_id}, {code})")
            except (httpx.HTTPError, ValueError) as exc:
                raise KisError(f"KIS 응답을 읽지 못했습니다 ({tr_id}).") from exc

    def offers(self, start: date, end: date):
        rows = []
        while start <= end:
            last = min(start + timedelta(days=27), end)
            continuation = ""
            seen = set()
            while True:
                data, more = self.get("/uapi/domestic-stock/v1/ksdinfo/pub-offer", "HHKDB669108C0", {
                    "SHT_CD": "", "F_DT": start.strftime("%Y%m%d"),
                    "T_DT": last.strftime("%Y%m%d"), "CTS": "",
                }, continuation)
                batch = data.get("output1")
                if not isinstance(batch, list):
                    raise KisError("KIS 일정 응답에 목록이 없습니다.")
                signature = json.dumps(batch, sort_keys=True)
                if signature in seen:
                    raise KisError("KIS 연속 조회에서 같은 페이지가 반복됐습니다.")
                seen.add(signature)
                rows.extend(batch)
                if more not in ("M", "F"):
                    break
                continuation = "N"
            start = last + timedelta(days=1)
        return rows

    def stock_info(self, code):
        data, _ = self.get("/uapi/domestic-stock/v1/quotations/search-stock-info",
                           "CTPF1002R", {"PRDT_TYPE_CD": "300", "PDNO": code})
        return data.get("output") or {}

    def daily_prices(self, code, day):
        data, _ = self.get("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                           "FHKST03010100", {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": day.strftime("%Y%m%d"), "FID_INPUT_DATE_2": day.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1",
        })
        return data.get("output2") or []


@cache
def kis_client():
    return KisClient()


def kis_date(value):
    value = (value or "").strip().replace("/", "-")
    return date.fromisoformat(value) if value and value != "00000000" else None


def is_regular_offer(name):
    excluded = ("기업인수목적", "스팩", "SPAC", "위탁관리부동산", "부동산투자회사")
    return bool(name) and not any(tag in name.upper() for tag in excluded) and not name.endswith("리츠")
