package com.chronoflow.local.domain

/** Privacy gate for foreground WeChat capture. Kept Android-free so its rules are testable. */
object ForegroundCaptureGuard {
    private val clock = Regex("^(?:今天|昨天)?\\s*\\d{1,2}:\\d{2}$")
    private val memberCount = Regex("\\s*[（(]\\d{1,4}[）)]\\s*$")
    private val controls = setOf(
        "微信", "通讯录", "发现", "我", "聊天信息", "返回", "更多", "发送", "按住 说话",
        "切换到键盘", "切换到语音输入", "表情", "加号", "图片", "拍摄", "视频通话",
    )

    fun allowedGroup(headerTexts: Collection<String>, preferences: Preferences): String? {
        if (!preferences.accessibilityCaptureEnabled) return null
        val allowed = preferences.groups.asSequence()
            .filter { it.source == Source.WECHAT }
            .map { it.name.trim() }
            .filter { it.isNotEmpty() }
            .toSet()
        val displayed = headerTexts.asSequence().map(String::trim).filter(String::isNotEmpty).toSet()
        return allowed.filter { name -> displayed.any { it == name || it.replace(memberCount, "").trim() == name } }
            .distinct()
            .singleOrNull()
    }

    fun messageCandidates(texts: Collection<String>, group: String): List<String> = texts.asSequence()
        .map { it.trim() }
        .filter { it.length in 2..10_000 }
        .filterNot { it == group || it in controls || clock.matches(it) }
        .filterNot { it.endsWith("条新消息") || it == "以下为新消息" || it == "查看更多消息" }
        .distinct()
        .toList()
}
