[app]
title = Cryptava
package.name = cryptava
package.domain = org.cryptava
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = kivy
orientation = portrait
osx.python_version = 3
osx.kivy_version = 1.9.1
fullscreen = 0
android.permissions = INTERNET

# Android specific settings to handle SDK and licenses automatically
android.api = 33
android.min_api = 21
android.sdk = 33
android.ndk = 25b
android.accept_sdk_license = True

skip_update = False
# Explicitly set python-for-android branch to avoid pip upgrade errors
p4a.branch = release