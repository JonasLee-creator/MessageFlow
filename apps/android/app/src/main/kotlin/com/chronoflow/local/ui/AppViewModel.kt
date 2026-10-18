package com.chronoflow.local.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.chronoflow.local.ChronoApplication
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class AppViewModel(application: Application) : AndroidViewModel(application) {
    val repository = (application as ChronoApplication).repository
    val state = repository.state
    private val mutableBusy = MutableStateFlow(false)
    val busy = mutableBusy.asStateFlow()
    val error = MutableStateFlow<String?>(null)
    init {
        run { repository.awaitReady(); if (repository.state.value.schedule.engine != "chronoflow-local") repository.change(replan = true) { it } }
    }
    fun run(action: suspend () -> Unit) {
        if (mutableBusy.value) return
        mutableBusy.value = true
        viewModelScope.launch {
            try { action(); error.value = null }
            catch (e: Exception) { error.value = e.message ?: "操作失败，请重试" }
            finally { mutableBusy.value = false }
        }
    }
}
