#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import traceback
# <xbar.title>Hot News</xbar.title>
# <xbar.version>v0.1.2</xbar.version>
# <xbar.author>quanhuynh</xbar.author>
# <xbar.author.github>ethanol1310</xbar.author.github>

from abc import ABC, abstractmethod
from datetime import timedelta, datetime

import pytz
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


class BaseCrawler(ABC):
    DEFAULT_SETTINGS = {
        "LOG_LEVEL": "ERROR",
        "DOWNLOAD_DELAY": 0.1,
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
    }

    USER_AGENT_SETTINGS = {
        "FAKEUSERAGENT_PROVIDERS": [
            "scrapy_fake_useragent.providers.FakeUserAgentProvider",
            "scrapy_fake_useragent.providers.FakerProvider",
            "scrapy_fake_useragent.providers.FixedUserAgentProvider",
        ],
        "FAKEUSERAGENT_FALLBACK": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/",
    }

    def __init__(self, tracker, start_date, end_date, settings_options=None):
        self.tracker = tracker
        self.start_date = start_date
        self.end_date = end_date
        self.settings_options = settings_options or {}
        self.process = self._create_crawler_process()

    def _create_crawler_process(self):
        settings = get_project_settings()

        combined_settings = self.DEFAULT_SETTINGS.copy()
        combined_settings.update(self.USER_AGENT_SETTINGS)

        custom_settings = self.settings_options.get("custom_settings", {})

        combined_settings.update(custom_settings)
        settings.update(combined_settings)

        return CrawlerProcess(settings)

    @abstractmethod
    def get_top_article_spider(self):
        pass

    def crawl_top_article(self):
        spider_class = self.get_top_article_spider()
        self.process.crawl(
            spider_class,
            tracker=self.tracker,
            start_date=self.start_date,
            end_date=self.end_date,
        )


class Article:
    def __init__(self, title, url, total_likes):
        self.title = title
        self.url = url
        self.total_likes = total_likes

    def __lt__(self, other):
        return self.total_likes < other.total_likes


class ArticleTracker:
    def __init__(self):
        self.articles = []

    def add_article(self, article):
        self.articles.append(article)

    def get_top_articles(self):
        self.articles.sort(reverse=True, key=lambda x: x.total_likes)
        return self.articles


class VnExpressCategory:
    def __init__(self, name, id, class_name, share_url):
        self.name = name
        self.id = id
        self.class_name = class_name
        self.share_url = share_url

    def __repr__(self):
        return f"Category(name='{self.name}', id={self.id}, class_name='{self.class_name}', share_url='{self.share_url}')"

class CrawlerManager:
    def __init__(self, crawlers):
        self.crawlers = crawlers

    def run_top_article_crawlers(self):
        for site_name, crawler in self.crawlers.items():
            crawler.crawl_top_article()

    def get_top_articles_by_crawler(self, crawler):
        return self.crawlers[crawler].tracker.get_top_articles()


class VnExpressCrawler(BaseCrawler):
    def get_top_article_spider(self):
        return VnExpressTopArticleSpider


class TuoiTreCrawler(BaseCrawler):
    def get_top_article_spider(self):
        return TuoiTreTopArticleSpider



class VnExpressTopArticleSpider(scrapy.Spider):
    name = "top_article_vnexpress"
    allowed_domains = ["vnexpress.net", "usi-saas.vnexpress.net"]

    def __init__(self, tracker, start_date, end_date, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = tracker
        self.base_url = "https://vnexpress.net"
        self.comment_api_url = "https://usi-saas.vnexpress.net/index/get"
        self.start_date_unix = int(start_date.timestamp())
        self.end_date_unix = int(end_date.timestamp())

    def start_requests(self):
        categories = self.fetch_categories()
        for category in categories:
            url = f"{self.base_url}/category/day/cateid/{category.id}/fromdate/{self.start_date_unix}/todate/{self.end_date_unix}/allcate/0/page/1"
            yield scrapy.Request(
                url=url, callback=self.parse, meta={"category": category}
            )

    def parse(self, response):
        articles = response.css("article.item-news.item-news-common")
        for article in articles:
            link = article.css("a::attr(href)").get()
            title = article.css("a::attr(title)").get()
            if link and title:
                yield scrapy.Request(
                    url=link,
                    callback=self.parse_article,
                    meta={"title": title, "url": link},
                )

        if articles:
            category = response.meta["category"]
            current_page = int(response.url.split("page/")[-1])
            next_page = current_page + 1
            next_url = f"{self.base_url}/category/day/cateid/{category.id}/fromdate/{self.start_date_unix}/todate/{self.end_date_unix}/allcate/0/page/{next_page}"
            yield scrapy.Request(
                url=next_url, callback=self.parse, meta={"category": category}
            )

    def parse_article(self, response):
        try:
            comment_section = response.css(
                "span.number_cmt.txt_num_comment.num_cmt_detail::attr(data-objectid)"
            ).get()
            if comment_section:
                object_id = comment_section
                object_type = response.css(
                    "span.number_cmt.txt_num_comment.num_cmt_detail::attr(data-objecttype)"
                ).get()
                if object_id and object_type:
                    url = f"{self.comment_api_url}?offset=0&limit=1000&sort_by=like&objectid={object_id}&objecttype={object_type}&siteid=1000000"
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse_comments,
                        meta={
                            "title": response.meta["title"],
                            "url": response.meta["url"],
                        },
                    )
        except Exception as e:
            print(message=f"Exception:{e}\n traceback:{traceback.format_exc()}")

    def parse_comments(self, response):
        try:
            data = response.json()
            comments = data.get("data", {}).get("items", [])
            total_likes = sum(comment["userlike"] for comment in comments)
            self.tracker.add_article(
                Article(response.meta["title"], response.meta["url"], total_likes)
            )
        except Exception as e:
            print(msg=f"Exception:{e}\n traceback:{traceback.format_exc()}")

    def fetch_categories(self):
        return [
            VnExpressCategory(
                name="Thời sự", id=1001005, class_name="thoisu", share_url="/thoi-su"
            ),
            VnExpressCategory(
                name="Góc nhìn", id=1003450, class_name="gocnhin", share_url="/goc-nhin"
            ),
            VnExpressCategory(
                name="Thế giới", id=1001002, class_name="thegioi", share_url="/the-gioi"
            ),
            VnExpressCategory(
                name="Video",
                id=1003834,
                class_name="video",
                share_url="https://video.vnexpress.net",
            ),
            VnExpressCategory(
                name="Podcasts", id=1004685, class_name="podcasts", share_url="/podcast"
            ),
            VnExpressCategory(
                name="Kinh doanh",
                id=1003159,
                class_name="kinhdoanh",
                share_url="/kinh-doanh",
            ),
            VnExpressCategory(
                name="Bất động sản",
                id=1005628,
                class_name="kinhdoanh",
                share_url="/bat-dong-san",
            ),
            VnExpressCategory(
                name="Khoa học", id=1001009, class_name="khoahoc", share_url="/khoa-hoc"
            ),
            VnExpressCategory(
                name="Giải trí", id=1002691, class_name="giaitri", share_url="/giai-tri"
            ),
            VnExpressCategory(
                name="Thể thao", id=1002565, class_name="thethao", share_url="/the-thao"
            ),
            VnExpressCategory(
                name="Pháp luật",
                id=1001007,
                class_name="phapluat",
                share_url="/phap-luat",
            ),
            VnExpressCategory(
                name="Giáo dục", id=1003497, class_name="giaoduc", share_url="/giao-duc"
            ),
            VnExpressCategory(
                name="Sức khỏe", id=1003750, class_name="suckhoe", share_url="/suc-khoe"
            ),
            VnExpressCategory(
                name="Đời sống", id=1002966, class_name="doisong", share_url="/doi-song"
            ),
            VnExpressCategory(
                name="Du lịch", id=1003231, class_name="dulich", share_url="/du-lich"
            ),
            VnExpressCategory(
                name="Số hóa", id=1002592, class_name="sohoa", share_url="/so-hoa"
            ),
            VnExpressCategory(
                name="Xe", id=1001006, class_name="xe", share_url="/oto-xe-may"
            ),
            VnExpressCategory(
                name="Ý kiến", id=1001012, class_name="ykien", share_url="/y-kien"
            ),
            VnExpressCategory(
                name="Tâm sự", id=1001014, class_name="tamsu", share_url="/tam-su"
            ),
            VnExpressCategory(
                name="Thư giãn", id=1001011, class_name="cuoi", share_url="/thu-gian"
            ),
        ]


class TuoiTreTopArticleSpider(scrapy.Spider):
    name = "top_article_tuoitre"
    allowed_domains = ["tuoitre.vn", "id.tuoitre.vn"]

    def __init__(self, tracker, start_date, end_date, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = tracker
        self.base_url = "https://tuoitre.vn"
        self.comment_api_url = "https://id.tuoitre.vn/api/getlist-comment.api"
        self.start_date = start_date
        self.end_date = end_date

    def start_requests(self):
        current_date = self.start_date
        while current_date <= self.end_date:
            date_str = current_date.strftime("%d-%m-%Y")
            url = f"{self.base_url}/timeline-xem-theo-ngay/0/{date_str}/trang-1.htm"
            yield scrapy.Request(
                url=url, callback=self.parse, meta={"date": date_str, "page": 1}
            )
            current_date += timedelta(days=1)

    def parse(self, response):
        articles = response.css("li.news-item")
        for article in articles:
            link = article.css("a::attr(href)").get()
            title = article.css("a::attr(title)").get()
            if link and title:
                article_url = f"{self.base_url}{link}"
                yield scrapy.Request(
                    url=article_url,
                    callback=self.parse_article,
                    meta={"title": title, "url": article_url},
                )

        if articles:
            date = response.meta["date"]
            current_page = response.meta["page"]
            next_page = current_page + 1
            next_url = (
                f"{self.base_url}/timeline-xem-theo-ngay/0/{date}/trang-{next_page}.htm"
            )
            yield scrapy.Request(
                url=next_url,
                callback=self.parse,
                meta={"date": date, "page": next_page},
            )

    def parse_article(self, response):
        try:
            comment_section = response.css("section.comment-wrapper")
            if comment_section:
                object_id = comment_section.css("::attr(data-objectid)").get()
                object_type = comment_section.css("::attr(data-objecttype)").get()
                if object_id and object_type:
                    url = f"{self.comment_api_url}?pageindex=1&objId={object_id}&objType={object_type}&sort=2"
                    yield scrapy.Request(
                        url=url,
                        callback=self.parse_comments,
                        meta={
                            "title": response.meta["title"],
                            "url": response.meta["url"],
                            "object_id": object_id,
                            "object_type": object_type,
                            "page": 1,
                            "total_likes": 0,
                        },
                    )
        except Exception as e:
            print(msg=f"Exception:{e}\n traceback:{traceback.format_exc()}")

    def parse_comments(self, response):
        try:
            data = response.json()
            comments = json.loads(data.get("Data", "[]"))
            total_likes = response.meta["total_likes"] + sum(
                sum(comment.get("reactions", {}).values()) for comment in comments
            )

            if comments:
                page = response.meta["page"] + 1
                url = f"{self.comment_api_url}?pageindex={page}&objId={response.meta['object_id']}&objType={response.meta['object_type']}&sort=2"
                yield scrapy.Request(
                    url=url,
                    callback=self.parse_comments,
                    meta={
                        "title": response.meta["title"],
                        "url": response.meta["url"],
                        "total_likes": total_likes,
                        "object_id": response.meta["object_id"],
                        "object_type": response.meta["object_type"],
                        "page": page,
                    },
                )
            else:
                self.tracker.add_article(
                    Article(response.meta["title"], response.meta["url"], total_likes)
                )
        except Exception as e:
            print(msg=f"Exception:{e}\n traceback:{traceback.format_exc()}")

settings_options = {
    'use_fake_useragent': True,
    'use_proxy': False,
    'custom_settings': {
        'DOWNLOAD_DELAY': 0.0,
    }
}

timezone_vn = pytz.timezone('Asia/Bangkok')
today = datetime.today()
start_date = today - timedelta(hours=4)
end_date = today

start_date = timezone_vn.localize(start_date)
end_date = timezone_vn.localize(end_date)

vnexpress_tracker = ArticleTracker()
tuoitre_tracker = ArticleTracker()

connectors = {
    "vnexpress": VnExpressCrawler(vnexpress_tracker, start_date, end_date, settings_options),
    "tuoitre": TuoiTreCrawler(tuoitre_tracker, start_date, end_date, settings_options)
}

manager = CrawlerManager(connectors)
manager.run_top_article_crawlers()

for connector in connectors.values():
    connector.process.start()

def print_top_articles(manager, crawler_name):
    top_articles = manager.get_top_articles_by_crawler(crawler_name)
    for i, article in enumerate(top_articles[:10], 1):
        print(f"{article.total_likes} - {article.title}| href={article.url}")

print(
    "| image=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"
)
print("---")
print("VnExpress")
print_top_articles(manager, "vnexpress")
print("---")
print("TuoiTre")
print_top_articles(manager, "tuoitre")
print("---")
