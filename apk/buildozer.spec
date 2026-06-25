[app]
title = Multporn下载器
package.name = multporndownloader
package.domain = com.multporn.downloader
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.0,requests,beautifulsoup4,urllib3,charset-normalizer,certifi,idna,soupsieve
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 34
android.minapi = 26
android.ndk = 25b
android.sdk = 34
android.arch = arm64-v8a
android.allow_backup = True
android.presplash_color = #1A1A2E

# 移除不必要的 gradle 依赖，避免构建冲突
# android.gradle_dependencies = 

log_level = 2
warn_on_root = 1
