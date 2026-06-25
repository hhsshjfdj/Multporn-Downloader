# Multporn 批量漫画下载器

multporn.net 漫画批量下载 Android 应用，支持 URL 直下 / 列表批量 / 关键词搜索。

## 直接安装

去 [Releases](../../releases) 下载最新 APK，安装到手机即可。

> APK 由 GitHub Actions 自动编译，每次推送代码自动出包。

## 功能

- 单部/多部漫画 URL 直接下载
- 分类页/标签页自动提取全部漫画批量下载
- 关键词搜索批量下载
- 多线程并发 + 断点续传
- 下载文件保存在 `内部存储/Multporn/`

## 自己构建

```bash
pip install buildozer
cd apk
buildozer android debug
```

## 免责声明

仅供学习交流，请遵守当地法律法规。
