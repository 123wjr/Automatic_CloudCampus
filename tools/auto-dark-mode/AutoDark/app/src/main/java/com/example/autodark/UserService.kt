package com.example.autodark

import android.os.IBinder
import java.io.BufferedReader

/**
 * Runs inside the process Shizuku spawns at **shell UID (2000)**. Shell holds
 * MODIFY_DAY_NIGHT_MODE on this device, so `cmd uimode night yes|no` flips the
 * global system theme — the one channel that actually re-themes the UI here.
 *
 * Must expose a no-arg (or Context) constructor; Shizuku instantiates it remotely.
 */
class UserService : IUserService.Stub {

    @Suppress("unused")
    constructor()

    override fun destroy() {
        System.exit(0)
    }

    override fun setNight(on: Boolean): Boolean {
        return try {
            val proc = Runtime.getRuntime()
                .exec(arrayOf("cmd", "uimode", "night", if (on) "yes" else "no"))
            // Drain output so the process can't block on a full pipe buffer.
            proc.inputStream.bufferedReader().use(BufferedReader::readText)
            proc.errorStream.bufferedReader().use(BufferedReader::readText)
            proc.waitFor() == 0
        } catch (t: Throwable) {
            false
        }
    }

    override fun asBinder(): IBinder = this
}
