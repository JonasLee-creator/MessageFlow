package com.chronoflow.local.domain

import java.net.URI

object AiApiPolicy {
    fun baseUrl(value: String): String {
        val uri = runCatching { URI(value.trim().trimEnd('/')) }.getOrNull()
            ?: error("请填写有效的 HTTPS 接口地址")
        require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.rawUserInfo == null &&
            uri.rawQuery == null && uri.rawFragment == null && uri.port in listOf(-1, 443)) {
            "接口须使用 HTTPS 默认端口，且不能包含账号、查询参数或片段"
        }
        return uri.toASCIIString().trimEnd('/')
    }

    fun completionUrl(base: String): String = baseUrl(base).let {
        if (it.endsWith("/chat/completions")) it else "$it/chat/completions"
    }

    fun secret(value: String, name: String = "API Key") {
        require(value.length in 8..512 && value.all { it.code in 33..126 }) { "$name 格式无效" }
    }

    fun validate(p: Preferences, officialAllowed: Boolean) {
        require(!p.aiEnabled || p.aiApiMode != ApiMode.OFFICIAL || officialAllowed) { "当前版本请使用用户接口" }
        if (!p.aiEnabled) return
        when (p.aiApiMode) {
            ApiMode.OFFICIAL -> {
                baseUrl(p.officialGatewayUrl)
                require(p.officialAccessCode.length in 16..128 && p.officialAccessCode.all { it.code in 33..126 }) { "请填写有效的官方接口体验码" }
            }
            ApiMode.USER -> {
                completionUrl(p.aiBaseUrl); secret(p.deepSeekApiKey)
                require(p.deepSeekModel.isNotBlank() && p.deepSeekModel.length <= 100 && p.deepSeekModel.none(Char::isWhitespace)) { "请填写有效的模型名称" }
            }
        }
    }
}
