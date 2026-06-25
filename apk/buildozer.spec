[app]

# 包名和应用名
title = Multporn下载器
package.name = multporndownloader
package.domain = org.multporn
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy,requests,beautifulsoup4,urllib3,charset-normalizer,certifi,idna
orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.2.1
fullscreen = 0

# 权限（网络+存储）
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 26
android.ndk = 25b
android.sdk = 33
android.gradle_dependencies = androidx.core:core:1.9.0
android.arch = arm64-v8a
android.allow_backup = True
android.presplash_color = #1A1A2E
android.icon = icon.png
android.presplash = presplash.png

# 日志
log_level = 2
warn_on_root = 1
