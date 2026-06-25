# Multporn 批量漫画下载器

专为 [multporn.net](https://multporn.net) 设计的批量漫画下载工具，支持 Windows / Android / Linux。

## 功能

- 单部 / 多部漫画 URL 直接下载
- 从分类页/标签页自动提取全部漫画批量下载
- 关键词搜索批量下载
- 多线程并发 + 断点续传
- 按漫画名自动建文件夹，图片编号命名

## 版本

| 版本 | 目录 | 说明 |
|------|------|------|
| 命令行版 | `multporn_downloader.py` | Python 脚本，全平台通用 |
| Windows 版 | `windows/` | 含 .bat 启动器，双击即用 |
| Android 版 | `apk/` | Kivy 项目，Buildozer 构建 APK |

## 快速开始（命令行版）

```bash
pip install requests beautifulsoup4 tqdm

# 下载单部
python multporn_downloader.py -u "https://multporn.net/comics/xxx"

# 批量下载
python multporn_downloader.py -u "链接1" -u "链接2" -u "链接3"

# 下载分类页下所有漫画
python multporn_downloader.py -l "https://multporn.net/new?type=1" --max 20

# 搜索并下载
python multporn_downloader.py -s "furry" --max 10 -o ./downloads -t 8
```

## Windows 版

解压 `windows/` 文件夹，双击 `启动下载器.bat`，菜单式交互操作。

## Android APK 构建

进入 `apk/` 目录，三种构建方式：

**Google Colab（推荐）：**
上传 apk 文件夹到 Colab，运行：
```python
!pip install buildozer cython
!buildozer android debug
```

**本地 Linux/WSL：**
```bash
pip install buildozer
buildozer android debug
```

详见 `apk/构建说明.txt`。

## 依赖

- Python 3.7+
- requests
- beautifulsoup4
- tqdm
- Kivy（仅 APK 版）

## 免责声明

本工具仅用于学习交流，请遵守当地法律法规，尊重版权。
