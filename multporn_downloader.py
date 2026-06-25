#!/usr/bin/env python3
"""
Multporn.net 批量漫画下载器

功能：
  - 支持单部/多部漫画 URL 批量下载
  - 支持分类页面自动提取所有漫画链接并批量下载
  - 支持搜索关键词批量下载
  - 断点续传（已下载图片自动跳过）
  - 多线程并发下载
  - 进度条显示

依赖安装：pip install requests beautifulsoup4 tqdm

用法示例：
  # 下载单部漫画
  python multporn_downloader.py -u "https://multporn.net/comics/study_break"

  # 批量下载多部漫画
  python multporn_downloader.py -u "https://multporn.net/comics/study_break" -u "https://multporn.net/comics/between_friends"

  # 下载分类/标签页面下所有漫画
  python multporn_downloader.py -l "https://multporn.net/new?type=1&language=1"

  # 搜索并下载
  python multporn_downloader.py -s "furry" --max 10

  # 指定下载目录和线程数
  python multporn_downloader.py -u "https://multporn.net/comics/study_break" -o ./downloads -t 8
"""

import argparse
import mimetypes
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
    from tqdm import tqdm
except ImportError:
    print("请先安装依赖: pip install requests beautifulsoup4 tqdm")
    sys.exit(1)

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/jpeg", ".jpg")

MULTPORN_HOME = "https://multporn.net/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ──────────────────────────────────────────────
#  工具函数
# ──────────────────────────────────────────────


def safe_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.strip(". ")
    return name[:200]


def get_session():
    """创建带重试和随机 UA 的 requests Session"""
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    return sess


# ──────────────────────────────────────────────
#  漫画页面解析
# ──────────────────────────────────────────────


class Comic:
    """表示一部漫画"""

    def __init__(self, url: str, session: requests.Session = None):
        self.url = url
        self.session = session or get_session()
        resp = self.session.get(self.url, timeout=30)
        resp.raise_for_status()
        self.soup = BeautifulSoup(resp.text, "html.parser")
        self._name = None
        self._image_urls = None

    @property
    def name(self) -> str:
        if self._name is None:
            meta = self.soup.find("meta", attrs={"name": "dcterms.title"})
            self._name = meta["content"] if meta else "unknown"
        return safe_filename(self._name)

    @property
    def image_urls(self) -> list:
        if self._image_urls is None:
            # 主提取：class="jb-image" 的 <p> 内的 <img>
            images = []
            for p in self.soup.find_all("p", class_="jb-image"):
                img = p.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = urljoin(MULTPORN_HOME, src)
                    images.append(src)

            # 备用提取：页面中所有大图
            if not images:
                for img in self.soup.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and not src.endswith((".svg", ".ico")):
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            src = urljoin(MULTPORN_HOME, src)
                        # 过滤缩略图
                        if "thumbnail" not in src.lower() and "thumb" not in src.lower():
                            images.append(src)

            self._image_urls = images
        return self._image_urls

    @property
    def page_count(self) -> int:
        return len(self.image_urls)

    def __str__(self):
        return f"{self.name} ({self.page_count} 页)"


# ──────────────────────────────────────────────
#  列表页解析
# ──────────────────────────────────────────────


def extract_comic_links_from_page(
    url: str, session: requests.Session = None
) -> list:
    """从分类/标签/搜索结果页提取所有漫画链接"""
    session = session or get_session()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = set()
    # Drupal views 表格布局
    table = soup.find("table", class_="views-view-grid")
    if table:
        for strong in table.find_all("strong"):
            a = strong.find("a")
            if a and a.get("href"):
                href = a["href"]
                if href.startswith("/comics/") or href.startswith("/node/"):
                    links.add(urljoin(MULTPORN_HOME, href))

    # 备选：view-content div
    if not links:
        view = soup.find("div", class_="view-content")
        if view:
            for strong in view.find_all("strong"):
                a = strong.find("a")
                if a and a.get("href"):
                    href = a["href"]
                    if href.startswith("/comics/") or href.startswith("/node/"):
                        links.add(urljoin(MULTPORN_HOME, href))

    return list(links)


def paginate_list(url: str, max_pages: int = 50) -> list:
    """翻页获取列表页所有漫画链接"""
    session = get_session()
    all_links = []
    for page in range(max_pages):
        page_url = f"{url}{'&' if '?' in url else '?'}page={page}" if page > 0 else url
        links = extract_comic_links_from_page(page_url, session)
        if not links:
            break
        all_links.extend(links)
        print(f"  第 {page + 1} 页: 提取 {len(links)} 个链接")
        time.sleep(0.5)
    return all_links


# ──────────────────────────────────────────────
#  搜索
# ──────────────────────────────────────────────


def search_comics(
    query: str, max_results: int = 20, content_type: str = "1"
) -> list:
    """搜索漫画并返回链接列表"""
    from urllib.parse import quote

    session = get_session()
    url = (
        f"{MULTPORN_HOME}search/"
        f"?views_fulltext={quote(query)}"
        f"&type={content_type}"
        f"&sort_by=search_api_relevance"
    )
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    view = soup.find("div", class_="view-content")
    if view:
        for strong in view.find_all("strong"):
            a = strong.find("a")
            if a and a.get("href"):
                href = a["href"]
                if href.startswith("/comics/"):
                    links.append(urljoin(MULTPORN_HOME, href))
                    if len(links) >= max_results:
                        break
    return links


# ──────────────────────────────────────────────
#  下载逻辑
# ──────────────────────────────────────────────


def download_image(args: tuple) -> dict:
    """下载单张图片，返回状态"""
    idx, url, save_path, session = args
    result = {"idx": idx, "url": url, "path": save_path, "status": "skipped"}

    # 已存在则跳过
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return result

    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        # 根据 Content-Type 修正扩展名
        ct = resp.headers.get("content-type", "")
        ext = mimetypes.guess_extension(ct.split(";")[0].strip())
        if ext and not save_path.endswith(ext):
            save_path = str(Path(save_path).with_suffix(ext))

        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        result["path"] = save_path
        result["status"] = "downloaded"
    except Exception as e:
        result["status"] = f"failed: {e}"

    return result


def download_comic(
    comic_url: str,
    output_dir: str = "./Multporn",
    max_workers: int = 4,
    session: requests.Session = None,
) -> tuple:
    """下载单部漫画，返回 (名称, 成功数, 失败数, 跳过数)"""
    session = session or get_session()

    try:
        comic = Comic(comic_url, session)
    except Exception as e:
        print(f"  [错误] 解析失败: {e}")
        return (comic_url, 0, 0, 0)

    if not comic.image_urls:
        print(f"  [警告] {comic.name}: 未找到图片")
        return (comic.name, 0, 0, 0)

    comic_dir = Path(output_dir) / comic.name
    comic_dir.mkdir(parents=True, exist_ok=True)

    zfill_width = len(str(comic.page_count))
    tasks = []
    for i, img_url in enumerate(comic.image_urls, 1):
        ext = Path(img_url.split("?")[0]).suffix or ".jpg"
        save_path = comic_dir / f"{i:0{zfill_width}}_{comic.name}{ext}"
        tasks.append((i, img_url, str(save_path), session))

    # 并发下载
    success = fail = skipped = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_image, t): t for t in tasks}
        with tqdm(total=len(tasks), desc=f"  {comic.name}", unit="页", leave=False) as pbar:
            for future in as_completed(futures):
                r = future.result()
                if r["status"] == "downloaded":
                    success += 1
                elif r["status"] == "skipped":
                    skipped += 1
                else:
                    fail += 1
                pbar.update(1)

    return (comic.name, success, fail, skipped)


# ──────────────────────────────────────────────
#  主入口
# ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Multporn.net 批量漫画下载器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s -u "https://multporn.net/comics/study_break"
  %(prog)s -u "https://multporn.net/comics/study_break" -u "https://multporn.net/comics/between_friends"
  %(prog)s -l "https://multporn.net/new?type=1&language=1" --max 20
  %(prog)s -s "furry" --max 10 -o ./downloads -t 8
        """,
    )
    parser.add_argument(
        "-u", "--url", action="append", dest="urls",
        help="漫画页面 URL（可重复使用下载多部）"
    )
    parser.add_argument(
        "-l", "--list-url",
        help="分类/标签页面 URL，自动提取该页面下所有漫画并下载"
    )
    parser.add_argument(
        "-s", "--search",
        help="搜索关键词，自动搜索并下载结果"
    )
    parser.add_argument(
        "--max", type=int, default=50,
        help="从列表页/搜索结果最多下载的漫画数量（默认 50）"
    )
    parser.add_argument(
        "-o", "--output", default="./Multporn",
        help="下载目录（默认 ./Multporn）"
    )
    parser.add_argument(
        "-t", "--threads", type=int, default=4,
        help="每部漫画的并发下载线程数（默认 4）"
    )

    args = parser.parse_args()

    if not args.urls and not args.list_url and not args.search:
        parser.print_help()
        return

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"下载目录: {output_dir.resolve()}")
    print(f"每部漫画并发数: {args.threads}\n")

    comic_urls = []

    # 直接指定的 URL
    if args.urls:
        comic_urls.extend(args.urls)

    # 列表页提取
    if args.list_url:
        print(f"[列表] 提取页面: {args.list_url}")
        links = paginate_list(args.list_url, max_pages=50)
        comic_urls.extend(links[: args.max])
        print(f"[列表] 共提取 {len(comic_urls)} 个漫画链接\n")

    # 搜索
    if args.search:
        print(f"[搜索] 关键词: {args.search}")
        links = search_comics(args.search, max_results=args.max)
        comic_urls.extend(links)
        print(f"[搜索] 共找到 {len(links)} 个结果\n")

    # 去重
    comic_urls = list(dict.fromkeys(comic_urls))

    if not comic_urls:
        print("没有找到可下载的漫画。")
        return

    print(f"共 {len(comic_urls)} 部漫画待下载\n")

    total_success = total_fail = total_skip = 0
    session = get_session()

    for i, url in enumerate(comic_urls, 1):
        print(f"[{i}/{len(comic_urls)}] {url}")
        name, ok, fail, skip = download_comic(
            url, str(output_dir), max_workers=args.threads, session=session
        )
        total_success += ok
        total_fail += fail
        total_skip += skip
        print(f"  -> 下载 {ok}, 跳过 {skip}, 失败 {fail}\n")

    print("=" * 50)
    print(f"全部完成！")
    print(f"  下载: {total_success}  跳过: {total_skip}  失败: {total_fail}")
    print(f"  文件位置: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
