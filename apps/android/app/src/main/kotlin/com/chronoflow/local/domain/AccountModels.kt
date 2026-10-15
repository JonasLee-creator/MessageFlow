package com.chronoflow.local.domain

data class LocalSession(val userId: String? = null, val username: String = "游客") {
    val isGuest: Boolean get() = userId == null
    val workspace: String get() = userId ?: "guest"
}

data class WorkspaceSnapshot(val session: LocalSession? = null, val state: LocalState = LocalState(), val version: Long = 0)

enum class ApiMode(val label: String) { OFFICIAL("官方接口"), USER("用户接口") }
