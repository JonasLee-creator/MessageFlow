package com.chronoflow.local

import android.app.Application
import com.chronoflow.local.data.LocalRepository
import com.chronoflow.local.notifications.Reminders
import kotlinx.coroutines.*

class ChronoApplication : Application() {
    val repository by lazy { LocalRepository(this) }
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    override fun onCreate() {
        super.onCreate()
        Reminders.createChannel(this)
        scope.launch {
            repository.state.collect { state -> runCatching { Reminders.arm(this@ChronoApplication, state) } }
        }
        scope.launch {
            runCatching {
                repository.awaitReady()
                if (repository.state.value.preferences.canvasEnabled) repository.syncCanvas()
            }
        }
    }
}
