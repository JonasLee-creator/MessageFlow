package com.chronoflow.local.domain

/** Independent of Android APIs so notification format handling is JVM-testable. */
data class MessagePart(val text: String, val sender: String = "", val timestamp: Long = 0)
data class NotificationEnvelope(
    val packageName: String, val key: String, val postedAt: Long,
    val title: String = "", val conversationTitle: String = "",
    val text: String = "", val bigText: String = "", val lines: List<String> = emptyList(),
    val messages: List<MessagePart> = emptyList(), val summary: Boolean = false,
    val subText: String = "",
)
object NotificationMatcher {
    fun relevant(text: String): Boolean = Regex("作业|实验|项目|报告|考试|提交|截止|延期|改到|改为|提前|推迟|上课|调课|取消|会议|班会|讲座|开会|截止|报名|答辩|deadline|assignment|quiz|meeting", RegexOption.IGNORE_CASE).containsMatchIn(text)

    private fun cleanTitle(title: String): String = title.trim()
        .replace(Regex("^\\[\\d+条(?:新消息|消息)?]\\s*"), "")
        .replace(Regex("(?:[·•|]\\s*)?[（(]?\\d+条(?:新消息|消息)[）)]?$"), "").trim()

    private fun titleMatches(candidate: String, name: String): Boolean {
        val clean = cleanTitle(candidate)
        return clean == name || Regex("^.+[（(]${Regex.escape(name)}[）)]$").matches(clean)
    }

    private fun bodyStartsWithGroup(candidate: String, name: String): Boolean = Regex(
        "^[\\[【]?${Regex.escape(name)}[\\]】]?\\s*(?:[:：·|]|[-—]\\s)"
    ).containsMatchIn(candidate.trim())

    fun extract(envelope: NotificationEnvelope, preferences: Preferences): List<Incoming> {
        if (!preferences.enabled) return emptyList()
        val source = Source.entries.firstOrNull { it != Source.MANUAL && it.packageName == envelope.packageName } ?: return emptyList()
        val allowed = preferences.groups.filter { it.source == source }.map { it.name }
        val bodies = envelope.messages.map { it.text } + envelope.lines + listOf(envelope.bigText, envelope.text)
        // Match exact system titles first; some ROMs place the WeChat group in subText or at the start of the body.
        val group = allowed.singleOrNull { name ->
            listOf(envelope.conversationTitle, envelope.title, envelope.subText).any { titleMatches(it, name) } ||
                bodies.any { bodyStartsWithGroup(it, name) }
        } ?: return emptyList()
        val parts = when {
            envelope.messages.isNotEmpty() -> envelope.messages
            envelope.lines.isNotEmpty() -> envelope.lines.map { MessagePart(it) }
            else -> listOf(MessagePart(envelope.bigText.ifBlank { envelope.text }))
        }
        return parts.filter { (preferences.aiEnabled || relevant(it.text)) && it.text.isNotBlank() && it.text.length <= 10000 }
            .map { part ->
                val stamp = part.timestamp.takeIf { it > 0 } ?: envelope.postedAt
                Incoming(source, group, part.text.trim(), java.time.Instant.ofEpochMilli(stamp), part.sender,
                    if (part.timestamp > 0) "${envelope.key}|${part.timestamp}|${part.sender}" else envelope.key)
            }.distinctBy { listOf(it.content, it.sender, it.receivedAt) }
    }
}
