import hashlib
import hmac
import json
import os
from configparser import ConfigParser
from datetime import datetime
from time import time
from urllib.parse import urlencode

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base = "https://picaapi.picacomic.com/"


class Pica:
    Order_Default = "ua"  # 默认
    Order_Latest = "dd"  # 新到旧
    Order_Oldest = "da"  # 旧到新
    Order_Loved = "ld"  # 最多爱心
    Order_Point = "vd"  # 最多指名

    def __init__(self) -> None:
        self.__s = requests.session()
        self.__s.verify = False
        parser = ConfigParser()
        parser.read('./config.ini', encoding='utf-8')
        self.headers = dict(parser.items('header'))

    def http_do(self, method, url, **kwargs):
        kwargs.setdefault("allow_redirects", True)
        header = self.headers.copy()
        ts = str(int(time()))
        raw = url.replace(base, "") + str(ts) + header["nonce"] + method + header["api-key"]
        print('PICA_SECRET_KEY: ' + os.environ["PICA_SECRET_KEY"], flush=True)
        hc = hmac.new(os.environ["PICA_SECRET_KEY"].encode(), digestmod=hashlib.sha256)
        hc.update(raw.lower().encode())
        header["signature"] = hc.hexdigest()
        header["time"] = ts
        kwargs.setdefault("headers", header)
        proxy = os.environ.get("REQUEST_PROXY")
        if proxy:
            proxies = {'http': proxy, 'https': proxy}
        else:
            proxies = None
        response = self.__s.request(method=method, url=url, verify=False, proxies=proxies, **kwargs)
        return response

    def login(self):
        url = base + "auth/sign-in"
        send = {"email": os.environ.get("PICA_ACCOUNT"), "password": os.environ.get("PICA_PASSWORD")}
        response = self.http_do("POST", url=url, json=send).text
        print("login response:{}".format(response), flush=True)
        if json.loads(response)["code"] != 200:
            raise Exception('PICA_ACCOUNT/PICA_PASSWORD ERROR')
        if 'token' not in response:
            raise Exception('PICA_SECRET_KEY ERROR')
        self.headers["authorization"] = json.loads(response)["data"]["token"]

    def comics(self, block="", tag="", order="", page=1):
        args = []
        if len(block) > 0:
            args.append(("c", block))
        if len(tag) > 0:
            args.append(("t", tag))
        if len(order) > 0:
            args.append(("s", order))
        if page > 0:
            args.append(("page", str(page)))
        params = urlencode(args)
        url = f"{base}comics?{params}"
        return self.http_do("GET", url).json()

    # 排行榜
    def leaderboard(self) -> list:
        # tt的可选值: H24, D7, D30   分别代表每天/周/月
        args = [("tt", 'H24'), ("ct", 'VC')]
        params = urlencode(args)
        url = f"{base}comics/leaderboard?{params}"
        res = self.http_do("GET", url)
        return json.loads(res.content.decode("utf-8"))["data"]["comics"]

    # 获取本子详细信息
    def comic_info(self, book_id):
        url = f"{base}comics/{book_id}"
        res = self.http_do("GET", url=url)
        return json.loads(res.content.decode())

    # 获取本子的章节 一页最大40条
    def episodes(self, book_id, page=1):
        url = f"{base}comics/{book_id}/eps?page={page}"
        return self.http_do("GET", url=url)

    # 获取本子的全部章节
    def episodes_all(self, book_id) -> list:
        first_page = self.episodes(book_id).json()
        pages = first_page["data"]["eps"]["pages"]
        total = first_page["data"]["eps"]["total"]
        episodes = list(first_page["data"]["eps"]["docs"])
        while pages > 1:
            episodes.extend(list(self.episodes(book_id, pages).json()["data"]["eps"]["docs"]))
            pages -= 1
        episodes = sorted(episodes, key=lambda x: x['order'])
        if len(episodes) != total:
            raise Exception('wrong number of episodes,expect:' + total + ',actual:' + len(episodes))
        return episodes

    # 根据章节获取图片
    def picture(self, book_id, ep_id, page=1):
        url = f"{base}comics/{book_id}/order/{ep_id}/pages?page={page}"
        return self.http_do("GET", url=url)

    def search(self, keyword, page=1, sort=Order_Latest):
        url = f"{base}comics/advanced-search?page={page}"
        res = self.http_do("POST", url=url, json={"keyword": keyword, "sort": sort})
        return json.loads(res.content.decode("utf-8"))["data"]["comics"]

    def search_all(self, keyword):
        comics = []
        if keyword:
            pages = self.search(keyword)["pages"]
            for page in range(1, pages + 1):
                docs = self.search(keyword, page)["docs"]
                res = [i for i in docs if
                       (datetime.now() - datetime.strptime(i["updated_at"], "%Y-%m-%dT%H:%M:%S.%fZ")).days <= int(
                           os.environ["SUBSCRIBE_DAYS"])]
                comics += res
                if len(docs) != len(res):
                    break
        return comics

    def categories(self):
        url = f"{base}categories"
        return self.http_do("GET", url=url)

    # 收藏/取消收藏本子
    def favourite(self, book_id):
        url = f"{base}comics/{book_id}/favourite"
        return self.http_do("POST", url=url)

    # 获取收藏夹-分页
    def my_favourite(self, page=1):
        url = f"{base}users/favourite?page={page}"
        res = self.http_do("GET", url=url)
        return json.loads(res.content.decode())["data"]["comics"]

    # 获取收藏夹-全部
    def my_favourite_all(self):
        comics = []
        pages = self.my_favourite()["pages"]
        for page in range(1, pages + 1):
            comics += self.my_favourite(page)["docs"]
        return comics

    # 打卡
    def punch_in(self):
        url = f"{base}/users/punch-in"
        res = self.http_do("POST", url=url)
        return json.loads(res.content.decode())
