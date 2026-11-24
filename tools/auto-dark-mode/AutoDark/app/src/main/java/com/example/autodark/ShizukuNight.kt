package com.example.autodark

import android.content.ComponentName
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import android.util.Log
import rikka.shizuku.Shizuku

/**
 * Owns the Shizuku connection and the bound [IUserService]. The user service runs
 * at shell UID and performs the actual global dark-mode switch.
 */
object ShizukuNight {
    private const val TAG = "ShizukuNight"
    const val PERMISSION_REQUEST_CODE = 1001

    @Volatile
    private var service: IUserService? = null
    private var binding = false

    private val userServiceArgs by lazy {
        Shizuku.UserServiceArgs(ComponentName(BuildConfig.APPLICATION_ID, UserService::class.java.name))
            .daemon(false)
            .processNameSuffix("nightsvc")
            .debuggable(BuildConfig.DEBUG)
            .version(1)
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            binding = false
            service = if (binder != null && binder.pingBinder()) {
                IUserService.Stub.asInterface(binder)
            } else null
            Log.i(TAG, "user service connected: ${service != null}")
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            service = null
            binding = false
            Log.i(TAG, "user service disconnected")
        }
    }

    /** Shizuku app installed and its service running. */
    fun isAvailable(): Boolean = try {
        Shizuku.pingBinder()
    } catch (t: Throwable) {
        false
    }

    fun hasPermission(): Boolean = try {
        isAvailable() && !Shizuku.isPreV11() &&
            Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
    } catch (t: Throwable) {
        false
    }

    fun requestPermission() {
        if (!isAvailable() || Shizuku.isPreV11()) return
        try {
            Shizuku.requestPermission(PERMISSION_REQUEST_CODE)
        } catch (t: Throwable) {
            Log.e(TAG, "requestPermission failed", t)
        }
    }

    /** Bind the shell-uid user service if not already bound. Safe to call repeatedly. */
    fun ensureBound() {
        if (service != null || binding || !hasPermission()) return
        binding = true
        try {
            Shizuku.bindUserService(userServiceArgs, connection)
        } catch (t: Throwable) {
            binding = false
            Log.e(TAG, "bindUserService failed", t)
        }
    }

    /**
     * Switch global dark mode. Returns true on success. If the service isn't bound
     * yet it kicks off binding and returns false; the next call (after the bind
     * completes) will succeed.
     */
    fun setNight(on: Boolean): Boolean {
        val s = service
        if (s == null) {
            ensureBound()
            return false
        }
        return try {
            s.setNight(on)
        } catch (t: Throwable) {
            Log.e(TAG, "setNight failed", t)
            service = null
            ensureBound()
            false
        }
    }
}
