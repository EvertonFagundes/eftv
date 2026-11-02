package com.eftv.android

import android.app.Application
import android.content.pm.ApplicationInfo
import timber.log.Timber

class EftvApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        val debuggable = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
        if (debuggable) {
            Timber.plant(Timber.DebugTree())
        }
    }
}
