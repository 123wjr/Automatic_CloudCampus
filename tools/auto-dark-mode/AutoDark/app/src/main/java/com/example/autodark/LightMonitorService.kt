package com.example.autodark

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.Log

/**
 * Foreground service: listens to the ambient light sensor and, when lux stays
 * below [threshold] for [debounceMs], flips global dark mode ON via Shizuku;
 * when it stays above for the same window, flips it OFF.
 */
class LightMonitorService : Service(), SensorEventListener {

    companion object {
        private const val TAG = "LightMonitor"
        private const val CHANNEL_ID = "auto_dark"
        private const val NOTIF_ID = 42

        const val EXTRA_THRESHOLD = "threshold"
        const val EXTRA_DEBOUNCE_MS = "debounce_ms"
        const val ACTION_STOP = "com.example.autodark.STOP"

        const val PREFS = "autodark"
        const val KEY_THRESHOLD = "threshold"
        const val KEY_DEBOUNCE = "debounce_ms"

        @Volatile var running: Boolean = false
            private set
        @Volatile var lastStatus: String = "未启动"
            private set
    }

    private lateinit var sensorManager: SensorManager
    private var lightSensor: Sensor? = null
    private lateinit var worker: HandlerThread
    private lateinit var handler: Handler

    private var threshold = 10f
    private var debounceMs = 2000L

    // null = not yet applied; true = dark; false = light
    private var lastApplied: Boolean? = null
    private var pendingTarget: Boolean? = null
    private var switchRunnable: Runnable? = null

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        lightSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT)
        worker = HandlerThread("monitor").apply { start() }
        handler = Handler(worker.looper)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        threshold = intent?.getFloatExtra(EXTRA_THRESHOLD, Float.NaN)
            ?.takeIf { !it.isNaN() }
            ?: prefs.getFloat(KEY_THRESHOLD, 10f)
        debounceMs = intent?.getLongExtra(EXTRA_DEBOUNCE_MS, -1L)
            ?.takeIf { it > 0 }
            ?: prefs.getLong(KEY_DEBOUNCE, 2000L)
        prefs.edit().putFloat(KEY_THRESHOLD, threshold).putLong(KEY_DEBOUNCE, debounceMs).apply()

        startForeground(NOTIF_ID, buildNotification("监听中 · 阈值 ${threshold}lux"),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)

        ShizukuNight.ensureBound()

        if (lightSensor == null) {
            updateStatus("本机无光线传感器")
        } else {
            // reset state so first reading is applied
            lastApplied = null
            pendingTarget = null
            sensorManager.registerListener(this, lightSensor, SensorManager.SENSOR_DELAY_NORMAL)
            running = true
            updateStatus("监听中 · 阈值 ${threshold}lux · 去抖 ${debounceMs}ms")
        }
        return START_STICKY
    }

    override fun onSensorChanged(event: SensorEvent) {
        val lux = event.values[0]
        val target = lux < threshold   // true => want dark
        handler.post { decide(lux, target) }
    }

    private fun decide(lux: Float, target: Boolean) {
        if (target == lastApplied) {
            cancelPending()
            updateStatus("%.1f lux · %s".format(lux, if (target) "暗黑" else "浅色"))
            return
        }
        if (pendingTarget == target) return  // already counting down to this state

        cancelPending()
        pendingTarget = target
        val r = Runnable {
            val ok = ShizukuNight.setNight(target)
            if (ok) {
                lastApplied = target
                updateStatus("已切换【%s】 (%.1f lux)".format(if (target) "暗黑" else "浅色", lux))
                Log.i(TAG, "switched night=$target at $lux lux")
            } else {
                // bind likely in progress — retry shortly
                updateStatus("切换待生效(等待 Shizuku) · %.1f lux".format(lux))
                handler.postDelayed({ if (pendingTarget == target) decide(lux, target) }, 600)
            }
            if (pendingTarget == target) pendingTarget = null
        }
        switchRunnable = r
        handler.postDelayed(r, debounceMs)
        updateStatus("%.1f lux %s 阈值 · 计时 %dms…".format(lux, if (target) "<" else "≥", debounceMs))
    }

    private fun cancelPending() {
        switchRunnable?.let { handler.removeCallbacks(it) }
        switchRunnable = null
        pendingTarget = null
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        running = false
        try { sensorManager.unregisterListener(this) } catch (_: Throwable) {}
        cancelPending()
        worker.quitSafely()
        updateStatus("已停止")
        super.onDestroy()
    }

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "自动暗黑模式", NotificationManager.IMPORTANCE_LOW)
        )
    }

    private fun buildNotification(text: String): Notification =
        Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("环境光自动暗黑")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .build()

    private fun updateStatus(text: String) {
        lastStatus = text
        try {
            getSystemService(NotificationManager::class.java)
                .notify(NOTIF_ID, buildNotification(text))
        } catch (_: Throwable) {}
    }
}
