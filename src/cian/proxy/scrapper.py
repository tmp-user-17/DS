import re
import random
import requests
from bs4 import BeautifulSoup
import js2py
from fake_useragent import UserAgent


def _get_request_key(session):
    res = session.post("https://spys.one/en/socks-proxy-list/")
    soup = BeautifulSoup(res.text, 'html.parser')
    return soup.find("input", {"name": "xx0"}).get("value")


def _get_proxy_list(session, xx0):
    res = session.post("https://spys.one/en/socks-proxy-list/",
        data=f"xx0={xx0}&xpp={0}&xf1={0}&xf2={0}&xf4={0}&xf5={2}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })

    soup = BeautifulSoup(res.text, 'html.parser')
    js = js2py.EvalJs({"document": {"write": lambda a: a}})
    js.execute(soup.select_one("body > script").string)

    addrs = soup.select("tr[onmouseover] > td:first-child")
    ports = [js.eval(i.find("script").string) for i in addrs]
    addrs = [i.get_text() for i in addrs]
    ports = [re.sub(r"<[^<]*>", "", i) for i in ports]

    return list(map(''.join, zip(addrs, ports)))


class ProxyScrapper:
    def __init__(self):
        self._proxies = []

    def refresh(self):
        session = requests.Session()
        session.headers["User-Agent"] = UserAgent().random
        print("Rotating proxy list")

        xx0 = _get_request_key(session)
        print(f"Got proxy request key xx0={xx0}")

        addrs = _get_proxy_list(session, xx0)
        self._proxies = [f"socks5://{i}" for i in addrs]
        print(f"Got {len(self._proxies)} proxies")

    def random(self):
        assert(len(self._proxies) > 0)
        return random.choice(self._proxies)
