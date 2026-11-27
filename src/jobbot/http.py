from __future__ import annotations
import time
import requests

UA = "jobbot/0.1 (personal job search; reads public job-board APIs)"
_s = requests.Session()
_s.headers["User-Agent"] = UA


def get(url, *, params=None, headers=None, retries=3, timeout=30, **kw):
    last = None
    for i in range(retries):
        try:
            r = _s.get(url, params=params, headers=headers, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** i); continue
            return r
        except requests.RequestException as e:
            last = e; time.sleep(2 ** i)
    if last:
        raise last
    return r


def request(method, url, *, retries=2, timeout=30, **kw):
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** i); continue
            return r
        except requests.RequestException as e:
            last = e; time.sleep(2 ** i)
    if last:
        raise last
    return r
