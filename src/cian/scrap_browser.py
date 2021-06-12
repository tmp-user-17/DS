from seleniumwire import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from time import sleep
import json
from .database import CianDatabase


class CianBrowser:
    def __init__(self, link, use_proxy=False):
        self._db = None
        self._driver = None
        self.title = None
        self.link = link
        self.results = {}

    def _init_driver(self):
        opts = Options()
        opts.add_argument("--lang=en")
        opts.add_argument("--headless")
        opts.add_argument("window-size=1920x1080")

        self._driver = webdriver.Chrome(options=opts)
        self._driver.scopes = [
            'https?://api.cian.ru/.*'
        ]
        self._driver.request_interceptor = lambda req: req.headers.replace_header('Accept-Encoding', 'identity')
        self._driver.response_interceptor = self._response_interceptor

    def _add_offers(self, offers):
        self.results.update({int(i['id']): i for i in offers})
        self._db.insert(offers)

    def _accept_cookies(self):
        try:
            accept_btn = self._driver.find_element_by_xpath("//*[@data-name='CookieAgreementBar']//button")
            accept_btn.send_keys(Keys.RETURN)
        except NoSuchElementException:
            pass
    
    def _response_interceptor(self, req, res):
        if req.url == "https://api.cian.ru/search-offers/v2/search-offers-desktop/":
            data = json.loads(res.body)
            if data['status'] == 'ok':
                self._add_offers(data['data']['offersSerialized'])
    
    def _get_next_page(self):
        old_url = self._driver.current_url

        try:
            # Find current page number
            current_page_span = self._driver.find_element_by_xpath("//*[@data-name='Pagination']//li/span")
            next_page = int(current_page_span.text) + 1

            # Find next page link and click it
            link = self._driver.find_element_by_xpath(f"//*[@data-name='Pagination']//li/a[normalize-space()={next_page}]")
            link.send_keys(Keys.RETURN)
        except NoSuchElementException:
            return False
        
        # Wait for loading (page url has changed)
        while self._driver.current_url == old_url:
            sleep(0.5)
        sleep(0.5)
        # Ensure that data was rendered into dom

        return True
    
    def _get_next_suggestion(self):
        def current_num():
            return len(self._driver.find_elements_by_xpath("//*[@data-name='Suggestions']/*[@data-name='CardComponent']"))
        old_num = current_num()

        try:
            # Find load next button and click it
            link = self._driver.find_element_by_xpath("//*[@data-name='Suggestions']/div/a[@href='#']")
            link.send_keys(Keys.RETURN)
        except NoSuchElementException:
            return False
        
        # Wait for loading (suggestions count has changed)
        while old_num == current_num():
            try:
                # Click that button again because it sometimes skips click
                link = self._driver.find_element_by_xpath("//*[@data-name='Suggestions']/div/a[@href='#']")
                link.send_keys(Keys.RETURN)
            except NoSuchElementException:
                pass
            sleep(0.5)

        return True

    def prepare(self):
        assert(self._db is None)
        self._db = CianDatabase()
        self._db.open()
        self._init_driver()

        self._driver.get(self.link)
        self._accept_cookies()

        script = "return window._cianConfig['frontend-serp'].filter(({key}) => key == 'initialState')[0].value"
        state = self._driver.execute_script(script)["results"]
        self.title = state["seo"]["h1"]
        self.link = state["paginationUrls"][0]

    def scrap(self, progress=None):
        assert(self._db is not None)
        assert(self._driver is not None)

        if progress:
            progress(0, 0)
        
        self._driver.get(self.link)
        self._accept_cookies()

        script = "return window._cianConfig['frontend-serp'].filter(({key}) => key == 'initialState')[0].value"
        state = self._driver.execute_script(script)
        self._add_offers(state["results"]["offers"])

        if progress:
            progress(1, len(self.results))

        pages = 0
        while self._get_next_page():
            pages += 1
            if progress:
                progress(1 + pages, len(self.results))

        # while self._get_next_suggestion():
        #     pages += 1
        #     if progress:
        #         progress(1 + pages, len(self._results))

        if progress:
            progress(1 + pages, len(self.results))
    
    def cleanup(self):
        assert(self._db is not None)
        assert(self._driver is not None)
        self._db.close()
        self._driver.quit()
        self._db = None
        self._driver = None
