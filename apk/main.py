#!/usr/bin/env python3
"""
Multporn 下载器 - Android APK 版
基于 Kivy 框架的 Android 应用

构建 APK 方法（在你的电脑上）:
  1. 安装 buildozer: pip install buildozer
  2. 进入项目目录: cd Multporn下载器_APK版
  3. 初始化: buildozer init
  4. 构建: buildozer android debug deploy run

或使用 Google Colab 在线构建（推荐）:
  上传整个项目文件夹到 Colab，运行 buildozer
"""

import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

# Kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.utils import platform

import mimetypes
import requests
from bs4 import BeautifulSoup

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/jpeg", ".jpg")

MULTPORN_HOME = "https://multporn.net/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ── 核心逻辑 ──

def get_session():
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    return sess


def safe_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name.strip(". ")[:200]


def parse_comic(url, session):
    """解析漫画页面，返回 (名称, 图片URL列表)"""
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 名称
    meta = soup.find("meta", attrs={"name": "dcterms.title"})
    name = safe_filename(meta["content"]) if meta else "unknown"

    # 图片
    images = []
    for p in soup.find_all("p", class_="jb-image"):
        img = p.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(MULTPORN_HOME, src)
            images.append(src)

    if not images:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and not src.endswith((".svg", ".ico")):
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = urljoin(MULTPORN_HOME, src)
                if "thumbnail" not in src.lower():
                    images.append(src)

    return name, images


def extract_links(url, session):
    """从列表页提取漫画链接"""
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()

    for tag in [soup.find("table", class_="views-view-grid"),
                soup.find("div", class_="view-content")]:
        if tag:
            for strong in tag.find_all("strong"):
                a = strong.find("a")
                if a and a.get("href"):
                    href = a["href"]
                    if href.startswith("/comics/"):
                        links.add(urljoin(MULTPORN_HOME, href))
    return list(links)


def search_comics(query, max_results, session):
    """搜索漫画"""
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
                if len(links) >= max_results:
                    break
    return links


def download_image(args):
    idx, url, save_path, session = args
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return ("skip", save_path)
    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        ext = mimetypes.guess_extension(ct.split(";")[0].strip())
        if ext and not save_path.endswith(ext):
            save_path = str(Path(save_path).with_suffix(ext))
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return ("ok", save_path)
    except Exception as e:
        return ("fail", str(e))


# ── UI ──

class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), **kwargs)
        self.session = get_session()
        self.downloading = False
        self.output_dir = None

        # 标题
        self.add_widget(Label(
            text="Multporn 漫画下载器",
            size_hint=(1, None), height=dp(40),
            font_size=dp(18), bold=True
        ))

        # Tab 切换
        self.tabs = TabbedPanel(
            do_default_tab=False, size_hint=(1, 1), tab_pos="top_left"
        )

        # Tab 1: URL输入
        tab_url = TabbedPanelItem(text="URL下载")
        tab_url.content = self._build_url_tab()
        self.tabs.add_widget(tab_url)

        # Tab 2: 列表页
        tab_list = TabbedPanelItem(text="批量列表")
        tab_list.content = self._build_list_tab()
        self.tabs.add_widget(tab_list)

        # Tab 3: 搜索
        tab_search = TabbedPanelItem(text="搜索")
        tab_search.content = self._build_search_tab()
        self.tabs.add_widget(tab_search)

        self.tabs.default_tab = tab_url
        self.add_widget(self.tabs)

        # 底部状态
        self.status_label = Label(
            text="就绪", size_hint=(1, None), height=dp(30),
            font_size=dp(12), color=(0.5, 0.5, 0.5, 1)
        )
        self.add_widget(self.status_label)

        self.progress = ProgressBar(
            max=100, value=0, size_hint=(1, None), height=dp(8)
        )
        self.add_widget(self.progress)

        # 设置输出目录
        if platform == "android":
            from android.storage import primary_external_storage_path
            self.output_dir = os.path.join(
                primary_external_storage_path(), "Multporn"
            )
        else:
            self.output_dir = os.path.join(os.getcwd(), "Downloads", "Multporn")

    def _build_url_tab(self):
        box = BoxLayout(orientation="vertical", padding=dp(5), spacing=dp(5))
        box.add_widget(Label(
            text="粘贴漫画URL（每行一个）:", size_hint=(1, None), height=dp(25)
        ))
        self.url_input = TextInput(
            hint_text="https://multporn.net/comics/xxx", size_hint=(1, 0.5),
            multiline=True
        )
        box.add_widget(self.url_input)
        btn = Button(
            text="开始下载", size_hint=(1, None), height=dp(45),
            background_color=(0.2, 0.6, 0.9, 1)
        )
        btn.bind(on_press=self.on_url_download)
        box.add_widget(btn)
        return box

    def _build_list_tab(self):
        box = BoxLayout(orientation="vertical", padding=dp(5), spacing=dp(5))
        box.add_widget(Label(
            text="分类/标签页URL:", size_hint=(1, None), height=dp(25)
        ))
        self.list_input = TextInput(
            hint_text="https://multporn.net/new?type=1",
            size_hint=(1, None), height=dp(40), multiline=False
        )
        box.add_widget(self.list_input)
        box.add_widget(Label(
            text="最大下载数:", size_hint=(1, None), height=dp(25)
        ))
        self.list_max = TextInput(
            text="20", size_hint=(1, None), height=dp(40),
            multiline=False, input_filter="int"
        )
        box.add_widget(self.list_max)
        btn = Button(
            text="提取并下载", size_hint=(1, None), height=dp(45),
            background_color=(0.2, 0.6, 0.9, 1)
        )
        btn.bind(on_press=self.on_list_download)
        box.add_widget(btn)
        return box

    def _build_search_tab(self):
        box = BoxLayout(orientation="vertical", padding=dp(5), spacing=dp(5))
        box.add_widget(Label(
            text="搜索关键词:", size_hint=(1, None), height=dp(25)
        ))
        self.search_input = TextInput(
            hint_text="furry", size_hint=(1, None), height=dp(40), multiline=False
        )
        box.add_widget(self.search_input)
        box.add_widget(Label(
            text="最大下载数:", size_hint=(1, None), height=dp(25)
        ))
        self.search_max = TextInput(
            text="10", size_hint=(1, None), height=dp(40),
            multiline=False, input_filter="int"
        )
        box.add_widget(self.search_max)
        btn = Button(
            text="搜索并下载", size_hint=(1, None), height=dp(45),
            background_color=(0.2, 0.6, 0.9, 1)
        )
        btn.bind(on_press=self.on_search_download)
        box.add_widget(btn)
        return box

    @mainthread
    def set_status(self, text):
        self.status_label.text = text

    @mainthread
    def set_progress(self, val):
        self.progress.value = val

    def _thread_download(self, urls):
        self.downloading = True
        total = len(urls)
        completed = 0
        total_ok = total_fail = total_skip = 0

        for url in urls:
            url = url.strip()
            if not url:
                continue

            self.set_status(f"解析: {url[:60]}...")
            try:
                name, image_urls = parse_comic(url, self.session)
            except Exception as e:
                self.set_status(f"解析失败: {e}")
                total_fail += 1
                completed += 1
                self.set_progress(int(completed / max(total, 1) * 100))
                continue

            if not image_urls:
                self.set_status(f"{name}: 未找到图片")
                completed += 1
                self.set_progress(int(completed / max(total, 1) * 100))
                continue

            comic_dir = Path(self.output_dir) / name
            comic_dir.mkdir(parents=True, exist_ok=True)

            zfill = len(str(len(image_urls)))
            tasks = []
            for i, img_url in enumerate(image_urls, 1):
                ext = Path(img_url.split("?")[0]).suffix or ".jpg"
                save_path = comic_dir / f"{i:0{zfill}}_{name}{ext}"
                tasks.append((i, img_url, str(save_path), self.session))

            ok = fail = skip = 0
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(download_image, t): t for t in tasks}
                for f in as_completed(futures):
                    s, _ = f.result()
                    if s == "ok":
                        ok += 1
                    elif s == "skip":
                        skip += 1
                    else:
                        fail += 1

            total_ok += ok
            total_fail += fail
            total_skip += skip
            completed += 1
            self.set_progress(int(completed / max(total, 1) * 100))
            self.set_status(f"[{completed}/{total}] {name}: 下载{ok} 跳过{skip} 失败{fail}")

        self.set_status(f"完成！下载{total_ok} 跳过{total_skip} 失败{total_fail}")
        self.progress.value = 100
        self.downloading = False

    def on_url_download(self, instance):
        if self.downloading:
            return
        urls = [u for u in self.url_input.text.split("\n") if u.strip()]
        if not urls:
            self.set_status("请先输入至少一个URL")
            return
        threading.Thread(target=self._thread_download, args=(urls,), daemon=True).start()

    def on_list_download(self, instance):
        if self.downloading:
            return
        url = self.list_input.text.strip()
        if not url:
            self.set_status("请输入列表页URL")
            return
        max_num = int(self.list_max.text or "20")
        threading.Thread(target=self._thread_list, args=(url, max_num), daemon=True).start()

    def _thread_list(self, url, max_num):
        self.downloading = True
        self.set_status("提取漫画链接中...")
        try:
            links = extract_links(url, self.session)[:max_num]
        except Exception as e:
            self.set_status(f"提取失败: {e}")
            self.downloading = False
            return
        if not links:
            self.set_status("未找到漫画链接")
            self.downloading = False
            return
        self.set_status(f"找到 {len(links)} 个漫画，开始下载...")
        self._thread_download(links)

    def on_search_download(self, instance):
        if self.downloading:
            return
        q = self.search_input.text.strip()
        if not q:
            self.set_status("请输入搜索关键词")
            return
        max_num = int(self.search_max.text or "10")
        threading.Thread(target=self._thread_search, args=(q, max_num), daemon=True).start()

    def _thread_search(self, query, max_num):
        self.downloading = True
        self.set_status(f"搜索: {query}...")
        try:
            links = search_comics(query, max_num, self.session)
        except Exception as e:
            self.set_status(f"搜索失败: {e}")
            self.downloading = False
            return
        if not links:
            self.set_status("未找到结果")
            self.downloading = False
            return
        self.set_status(f"找到 {len(links)} 个结果，开始下载...")
        self._thread_download(links)


class MultpornApp(App):
    def build(self):
        Window.minimum_width = dp(320)
        Window.minimum_height = dp(500)
        return MainLayout()


if __name__ == "__main__":
    MultpornApp().run()
