#!/bin/bash
# the widget's APK without Gradle (Ubuntu's android-sdk-platform-23, aapt, dalvik-exchange, apksigner, zipalign):
# res -> R.java -> javac (Java 8) -> classes.dex -> the APK, signed by a local key (build/vp.keystore, not in git)
set -e; cd "$(dirname "$0")"
SDK=/usr/lib/android-sdk/platforms/android-23/android.jar; B=build
rm -rf $B/gen $B/obj $B/apk; mkdir -p $B/gen $B/obj $B/apk
python3 make_icon.py res/drawable/icon.png
aapt package -f -m -J $B/gen -M AndroidManifest.xml -S res -I $SDK
javac -nowarn --release 8 -cp $SDK -d $B/obj $B/gen/com/vppoc/widget/R.java src/com/vppoc/widget/*.java 2>&1 | grep -v "^warning\|^Note\|^1 warning" || true
dalvik-exchange --dex --output=$B/apk/classes.dex $B/obj
aapt package -f -M AndroidManifest.xml -S res -I $SDK -F $B/unsigned.apk $B/apk
[ -f $B/vp.keystore ] || keytool -genkeypair -keystore $B/vp.keystore -storepass vpwidget -keypass vpwidget -alias vp -keyalg RSA \
  -keysize 2048 -validity 10000 -dname "CN=VP-POC widget" >/dev/null 2>&1
zipalign -f 4 $B/unsigned.apk $B/aligned.apk
apksigner sign --ks $B/vp.keystore --ks-pass pass:vpwidget --key-pass pass:vpwidget --out $B/vp-widget.apk $B/aligned.apk
apksigner verify $B/vp-widget.apk && ls -la $B/vp-widget.apk
