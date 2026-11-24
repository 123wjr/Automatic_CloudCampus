package com.example.autodark

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import com.example.autodark.databinding.ActivityMainBinding
import rikka.shizuku.Shizuku

class MainActivity : Activity() {

    private lateinit var b: ActivityMainBinding

    private val permListener = Shizuku.OnRequestPermissionResultListener { requestCode, grantResult ->
        if (requestCode == ShizukuNight.PERMISSION_REQUEST_CODE) {
            val granted = grantResult == PackageManager.PERMISSION_GRANTED
            toast(if (granted) "Shizuku 已授权" else "Shizuku 授权被拒绝")
            if (granted) ShizukuNight.ensureBound()
            refresh()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)

        Shizuku.addRequestPermissionResultListener(permListener)

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 2)
        }

        b.grant.setOnClickListener {
            when {
                !ShizukuNight.isAvailable() ->
                    toast("请先安装并通过 adb 启动 Shizuku 服务")
                ShizukuNight.hasPermission() -> {
                    ShizukuNight.ensureBound(); toast("已授权"); refresh()
                }
                else -> ShizukuNight.requestPermission()
            }
        }

        b.start.setOnClickListener { startMonitoring() }

        b.stop.setOnClickListener {
            startService(Intent(this, LightMonitorService::class.java).setAction(LightMonitorService.ACTION_STOP))
            refresh()
        }
    }

    private fun startMonitoring() {
        if (!ShizukuNight.hasPermission()) {
            toast("请先完成 ① 授权 Shizuku")
            ShizukuNight.requestPermission()
            return
        }
        val threshold = b.threshold.text.toString().toFloatOrNull() ?: 10f
        val debounceMs = ((b.debounce.text.toString().toFloatOrNull() ?: 2f) * 1000).toLong()
        val i = Intent(this, LightMonitorService::class.java)
            .putExtra(LightMonitorService.EXTRA_THRESHOLD, threshold)
            .putExtra(LightMonitorService.EXTRA_DEBOUNCE_MS, debounceMs)
        startForegroundService(i)
        toast("已开始监听")
        refresh()
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    override fun onDestroy() {
        Shizuku.removeRequestPermissionResultListener(permListener)
        super.onDestroy()
    }

    private fun refresh() {
        b.shizukuState.text = when {
            !ShizukuNight.isAvailable() -> "Shizuku：未运行（需安装并 adb 启动）"
            ShizukuNight.hasPermission() -> "Shizuku：已连接并授权 ✓"
            else -> "Shizuku：运行中，但未授权（点①）"
        }
        b.status.text = LightMonitorService.lastStatus +
            if (LightMonitorService.running) "（监听中）" else ""
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_SHORT).show()
}
