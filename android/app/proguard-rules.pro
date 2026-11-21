# ProGuard rules for EFTV Android

# Keep Chaquopy classes
-keep class com.chaquo.python.** { *; }

# Keep our classes
-keep class com.eftv.android.** { *; }

# Keep WebView JavaScript interface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Keep Kotlin metadata
-keep class kotlin.Metadata { *; }

# QR code (assinatura na TV): evita que o R8 remova classes usadas em runtime
-keep class com.google.zxing.** { *; }

# Keep aiohttp classes
-keep class org.apache.http.** { *; }
-keep class org.apache.commons.logging.** { *; }

# Keep aiohttp web classes
-keep class aiohttp.** { *; }
-keep class multidict.** { *; }
-keep class yarl.** { *; }

# Keep asyncio
-keep class asyncio.** { *; }

# Keep JSON libraries
-keep class org.json.** { *; }
-keep class com.google.gson.** { *; }

# Keep WebView classes
-keep class android.webkit.** { *; }