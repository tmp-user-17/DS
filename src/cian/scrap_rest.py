from time import sleep
import requests
from bs4 import BeautifulSoup
import js2py
from .proxy import ProxyScrapper


def _has_captcha(content):
    soup = BeautifulSoup(content, 'html.parser')
    captcha = soup.find('div', {'id': 'captcha'})
    return captcha is not None


class CianRest:
    def __init__(self, link, use_proxy=False):
        self._use_proxy = use_proxy
        self._proxies = None

        self._session = requests.Session()
        self._session.verify = False
        self._session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"

        self._query = None
        self.link = link
        self.title = None
        self.results = {}

    def _add_offers(self, offers):
        self.results.update({int(i['id']): i for i in offers})

    def _get_initial_state(self):
        if self._proxies:
            self._session.proxies = {"https": self._proxies.random()}
        res = self._session.get(self.link)
        res.raise_for_status()
        assert(not _has_captcha(res.text))

        soup = BeautifulSoup(res.text, 'html.parser')

        scripts = soup.find_all('script', {'src': None})
        scripts = [i.string for i in scripts if "frontend-serp" in i.string and "initialState" in i.string]
        assert(len(scripts) == 1)

        js = js2py.EvalJs()
        js.execute(scripts[0])
        config = js.eval("window._cianConfig").to_dict()

        state = [i for i in config["frontend-serp"] if i["key"] == "initialState"][0]["value"]
        state = state["results"]
        return state["seo"]["h1"], state["paginationUrls"][0], state["jsonQuery"]
    
    def _get_page_offers(self, query, page):
        query["page"] = {"type": "term", "value": page}
        query = {"jsonQuery": query}

        url = "https://api.cian.ru/search-offers/v2/search-offers-desktop/"

        if self._proxies:
            self._session.proxies = {"https": self._proxies.random()}
        res = self._session.post(url, json=query)
        res.raise_for_status()
        assert(not _has_captcha(res.text))

        sleep(1)

        data = res.json()
        assert(data["status"] == "ok")

        return data["data"]["offersSerialized"]

    def prepare(self):
        assert(self._proxies is None)
        if self._use_proxy:
            self._proxies = ProxyScrapper()
            self._proxies.refresh()
        self.title, self.link, self._query = self._get_initial_state()

    def scrap(self, progress=None):
        if self._use_proxy:
            assert (self._proxies is not None)

        if progress:
            progress(0, 0)

        pages = 0
        while True:
            offers = self._get_page_offers(self._query, pages + 1)
            if len(offers) == 0:
                break
            pages += 1
            self._add_offers(offers)
            if progress:
                progress(pages, len(self.results))

    def cleanup(self):
        self._proxies = None
