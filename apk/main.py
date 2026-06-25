#!/usr/bin/env python3
"""
Multporn 下载器 - Android APK 版
基于 Kivy 框架，支持 URL输入 / 列表批量 / 关键词搜索 三种模式
"""

import os, re, sys, threading, mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.progressbar import ProgressBar
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.utils import platform

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/jpeg", ".jpg")

MULTPORN_HOME = "https://multporn.net/"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"


def get_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def safe_name(s):
    return re.sub(r'[\\/*?:"<>|]', "_", s).strip(". ")[:200]


def parse_comic(url, session):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    meta = soup.find("meta", attrs={"name": "dcterms.title"})
    name = safe_name(meta["content"]) if meta else "unknown"
    images = []
    for p in soup.find_all("p", class_="jb-image"):
        img = p.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("//"): src = "https:" + src
            elif src.startswith("/"): src = urljoin(MULTPORN_HOME, src)
            images.append(src)
    if not images:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and not src.endswith((".svg", ".ico")):
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = urljoin(MULTPORN_HOME, src)
                if "thumb" not in src.lower():
                    images.append(src)
    return name, images


def extract_links(url, session):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()
    for tag in [soup.find("table", class_="views-view-grid"),
                soup.find("div", class_="view-content")]:
        if tag:
            for strong in tag.find_all("strong"):
                a = strong.find("a")
                if a and a.get("href") and a["href"].startswith("/comics/"):
                    links.add(urljoin(MULTPORN_HOME, a["href"]))
    return list(links)


def search_comics(query, max_r, session):
    from urllib.parse import quote
    url = f"{MULTPORN_HOME}search/?views_fulltext={quote(query)}&type=1&sort_by=search_api_relevance"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    view = soup.find("div", class_="view-content")
    if view:
        for strong in view.find_all("strong"):
            a = strong.find("a")
            if a and a.get("href") and a["href"].startswith("/comics/"):
                links.append(urljoin(MULTPORN_HOME, a["href"]))
                if len(links) >= max_r:
                    break
    return links


def download_one(args):
    idx, url, path, session = args
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return ("skip", path)
    try:
        r = session.get(url, timeout=60, stream=True)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        ext = mimetypes.guess_extension(ct.split(";")[0].strip())
        if ext and not path.endswith(ext):
            path = str(Path(path).with_suffix(ext))
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return ("ok", path)
    except Exception as e:
        return ("fail", str(e))


class MainUI(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), **kw)
        self.session = get_session()
        self.busy = False

        if platform == "android":
            from android.storage import primary_external_storage_path
            self.out = os.path.join(primary_external_storage_path(), "Multporn")
        else:
            self.out = os.path.join(os.getcwd(), "Multporn")

        self.add_widget(Label(text="Multporn 漫画下载器", size_hint=(1, None),
                              height=dp(40), font_size=dp(18), bold=True))

        tabs = TabbedPanel(do_default_tab=False, size_hint=(1, 1), tab_pos="top_left")

        # Tab1: URL
        t1 = TabbedPanelItem(text="URL下载")
        b1 = BoxLayout(orientation="vertical", padding=dp(5), spacing=dp(5))
        b1.add_widget(Label(text="粘贴漫画URL（一行一个）:", size_hint=(1, None), height=dp(22)))
        self.url_in = TextInput(hint_text="https://multporn.net/comics/xxx", multiline=True)
        b1.add_widget(self.url_in)
        btn1 = Button(text="开始下载", size_hint=(1, None), height=dp(45),
                      background_color=(0.18, 0.55, 0.85, 1))
        btn1.bind(on_press=self.do_url)
        b1.add_widget(btn1)
        t1.content = b1
        tabs.add_widget(t1)

        # Tab2: 列表
        t2 = TabbedPanelItem(text="批量列表")
        b2 = BoxLayout(orientation="vertical", padding=dp(5), spacing=dp(5))
        b2.add_widget(Label(text="分类/标签页URL:", size_hint=(1, None), height=dp(22)))
        self.list_in = TextInput(hint_text="https://multporn.net/new?type=1", multiline=False,
                                 size_hint=(1, None), height=dp(40))
        b2.add_widget(self.list_in)
        b2.add_widget(Label(text="最大下载数:", size_hint=(1, None), height=dp(22)))
        self.list_max = TextInput(text="20", multiline=False, size_hint=(1, None), height=dp(40),
                                  input_filter="int")
        b2.add_widget(self.list_max)
        btn2 = Button(text="提取并下载", size_hint=(1, None), height=dp(45),
                      background_color=(0.18, 0.55, 0.85, 1))
        btn2.bind(on_press=self.do_list)
        b2.add_widget(btn2)
        t2.content = b2
        tabs.add_widget(t2)

        # Tab3: 搜索
        t3 = TabbedPanelItem(text="搜索")
        b3 = BoxLayout(orientation="vertical", padding=dp(5), spacing=dp(5))
        b3.add_widget(Label(text="搜索关键词:", size_hint=(1, None), height=dp(22)))
        self.search_in = TextInput(hint_text="furry", multiline=False,
                                   size_hint=(1, None), height=dp(40))
        b3.add_widget(self.search_in)
        b3.add_widget(Label(text="最大下载数:", size_hint=(1, None), height=dp(22)))
        self.search_max = TextInput(text="10", multiline=False, size_hint=(1, None), height=dp(40),
                                    input_filter="int")
        b3.add_widget(self.search_max)
        btn3 = Button(text="搜索并下载", size_hint=(1, None), height=dp(45),
                      background_color=(0.18, 0.55, 0.85, 1))
        btn3.bind(on_press=self.do_search)
        b3.add_widget(btn3)
        t3.content = b3
        tabs.add_widget(t3)

        tabs.default_tab = t1
        self.add_widget(tabs)

        self.status = Label(text="就绪", size_hint=(1, None), height=dp(28),
                            font_size=dp(11), color=(0.5, 0.5, 0.5, 1))
        self.add_widget(self.status)
        self.pbar = ProgressBar(max=100, value=0, size_hint=(1, None), height=dp(6))
        self.add_widget(self.pbar)

        # 底部提示
        self.add_widget(Label(
            text="下载文件保存在 内部存储/Multporn/",
            size_hint=(1, None), height=dp(24),
            font_size=dp(10), color=(0.4, 0.4, 0.4, 1)
        ))

    @mainthread
    def st(self, t):
        self.status.text = t

    @mainthread
    def pb(self, v):
        self.pbar.value = v

    def _dl(self, urls):
        self.busy = True
        total = len(urls)
        done = 0
        tok = tfail = tskip = 0
        for u in urls:
            u = u.strip()
            if not u: continue
            self.st(f"解析: {u[:50]}...")
            try:
                name, imgs = parse_comic(u, self.session)
            except Exception as e:
                self.st(f"解析失败: {e}")
                tfail += 1; done += 1
                self.pb(int(done / max(total, 1) * 100))
                continue
            if not imgs:
                self.st(f"{name}: 无图片")
                done += 1
                self.pb(int(done / max(total, 1) * 100))
                continue
            d = Path(self.out) / name
            d.mkdir(parents=True, exist_ok=True)
            zw = len(str(len(imgs)))
            tasks = []
            for i, img in enumerate(imgs, 1):
                ext = Path(img.split("?")[0]).suffix or ".jpg"
                sp = d / f"{i:0{zw}}_{name}{ext}"
                tasks.append((i, img, str(sp), self.session))
            ok = fail = skip = 0
            with ThreadPoolExecutor(max_workers=4) as pool:
                fs = {pool.submit(download_one, t): t for t in tasks}
                for f in as_completed(fs):
                    s, _ = f.result()
                    if s == "ok": ok += 1
                    elif s == "skip": skip += 1
                    else: fail += 1
            tok += ok; tfail += fail; tskip += skip
            done += 1
            self.pb(int(done / max(total, 1) * 100))
            self.st(f"[{done}/{total}] {name}: 下载{ok} 跳过{skip} 失败{fail}")
        self.st(f"完成！下载{tok} 跳过{tskip} 失败{tfail}")
        self.pb(100)
        self.busy = False

    def do_url(self, _):
        if self.busy: return
        urls = [u for u in self.url_in.text.split("\n") if u.strip()]
        if not urls: self.st("请输入至少一个URL"); return
        threading.Thread(target=self._dl, args=(urls,), daemon=True).start()

    def do_list(self, _):
        if self.busy: return
        u = self.list_in.text.strip()
        if not u: self.st("请输入列表页URL"); return
        mx = int(self.list_max.text or "20")
        threading.Thread(target=self._do_list, args=(u, mx), daemon=True).start()

    def _do_list(self, u, mx):
        self.busy = True
        self.st("提取链接中...")
        try:
            links = extract_links(u, self.session)[:mx]
        except Exception as e:
            self.st(f"提取失败: {e}"); self.busy = False; return
        if not links: self.st("未找到漫画链接"); self.busy = False; return
        self.st(f"找到 {len(links)} 部，开始下载...")
        self._dl(links)

    def do_search(self, _):
        if self.busy: return
        q = self.search_in.text.strip()
        if not q: self.st("请输入关键词"); return
        mx = int(self.search_max.text or "10")
        threading.Thread(target=self._do_search, args=(q, mx), daemon=True).start()

    def _do_search(self, q, mx):
        self.busy = True
        self.st(f"搜索: {q}...")
        try:
            links = search_comics(q, mx, self.session)
        except Exception as e:
            self.st(f"搜索失败: {e}"); self.busy = False; return
        if not links: self.st("未找到结果"); self.busy = False; return
        self.st(f"找到 {len(links)} 个，开始下载...")
        self._dl(links)


class MultpornApp(App):
    def build(self):
        Window.minimum_width = dp(320)
        Window.minimum_height = dp(500)
        return MainUI()


if __name__ == "__main__":
    MultpornApp().run()
