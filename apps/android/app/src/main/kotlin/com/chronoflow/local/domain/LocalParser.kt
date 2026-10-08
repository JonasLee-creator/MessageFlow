package com.chronoflow.local.domain

import java.time.*

/** A deliberately conservative offline rule engine. It is not a cloud LLM. */
object LocalParser {
    private data class Evidence(val date: LocalDate?, val times: List<LocalTime>, val notes: List<String>)
    private fun number(text: String): Int? {
        text.toIntOrNull()?.let { return it }
        val digits = mapOf('零' to 0, '一' to 1, '二' to 2, '两' to 2, '三' to 3, '四' to 4, '五' to 5, '六' to 6, '七' to 7, '八' to 8, '九' to 9)
        if (text == "十") return 10
        if ('十' in text) {
            val parts = text.split('十')
            val tens = if (parts[0].isEmpty()) 1 else digits[parts[0].singleOrNull()] ?: return null
            val ones = if (parts.getOrElse(1) { "" }.isEmpty()) 0 else digits[parts[1].singleOrNull()] ?: return null
            return tens * 10 + ones
        }
        return digits[text.singleOrNull()]
    }

    private fun dates(text: String, reference: ZonedDateTime): Evidence {
        val notes = mutableListOf<String>()
        val found = mutableListOf<Pair<Int, LocalDate?>>()
        Regex("(?<![\\d:：])(?:(20\\d{2})[-/年])?(\\d{1,2})[-/月](\\d{1,2})(?:日|号)?(?![\\d:：])").findAll(text).forEach { m ->
            val year = m.groupValues[1].toIntOrNull() ?: reference.year
            val parsed = runCatching { LocalDate.of(year, m.groupValues[2].toInt(), m.groupValues[3].toInt()) }.getOrNull()
            if (parsed == null) notes += "日期无效，请手动填写"
            found += m.range.first to parsed
        }
        Regex("今天|今日|今晚|明天|明日|后天").findAll(text).forEach { m ->
            val days = when (m.value) { "明天", "明日" -> 1L; "后天" -> 2L; else -> 0L }
            found += m.range.first to reference.toLocalDate().plusDays(days)
        }
        Regex("(下周|下星期|本周|这周|周|星期)([一二三四五六日天])").findAll(text).forEach { m ->
            val day = "一二三四五六日天".indexOf(m.groupValues[2]).coerceAtMost(6) + 1
            var delta = day - reference.dayOfWeek.value
            if (m.groupValues[1].startsWith("下")) delta += 7
            else if (delta < 0 && m.groupValues[1] !in listOf("本周", "这周")) delta += 7
            found += m.range.first to reference.toLocalDate().plusDays(delta.toLong())
        }
        if (found.size > 1) notes += "包含多个日期，请核对最终日期"
        if (found.isEmpty()) notes += "没有明确日期，请补充"
        val times = mutableListOf<LocalTime>()
        var inheritedPeriod = ""
        val pattern = Regex("(凌晨|早上|上午|中午|下午|晚上|晚间)?\\s*(\\d{1,2}|[一二三四五六七八九十两]+)(?:[:：](\\d{2})|点(?:(半)|((?:\\d{1,2}|[一二三四五六七八九十]+))分?)?|时)")
        pattern.findAll(text).forEach { m ->
            val period = m.groupValues[1].ifBlank { inheritedPeriod }
            if (m.groupValues[1].isNotBlank()) inheritedPeriod = m.groupValues[1]
            var hour = number(m.groupValues[2]) ?: return@forEach
            if (period.isBlank() && hour in 1..11 && m.groupValues[3].isBlank()) notes += "未说明上午或下午，请核对时间"
            val minute = when {
                m.groupValues[3].isNotBlank() -> m.groupValues[3].toInt()
                m.groupValues[4] == "半" -> 30
                m.groupValues[5].isNotBlank() -> number(m.groupValues[5]) ?: -1
                else -> 0
            }
            if (period in listOf("下午", "晚上", "晚间") && hour in 1..11) hour += 12
            if (period == "中午" && hour in 1..10) hour += 12
            if (period == "凌晨" && hour == 12) hour = 0
            val time = runCatching { LocalTime.of(hour, minute) }.getOrNull()
            if (time != null) times += time else notes += "时间无效，请手动填写"
        }
        if (Regex("[一二三四五六七八九十两\\d]+点\\d{3,}").containsMatchIn(text)) notes += "时间格式不明确"
        return Evidence(found.maxByOrNull { it.first }?.second, times, notes.distinct())
    }

    private fun subject(text: String): String {
        Regex("(?:实验|作业|报告)[一二三四五六七八九十\\d]+", RegexOption.IGNORE_CASE).find(text)?.let { return it.value }
        var clean = text.replace(Regex("^.{1,24}[:：]\\s*(?!\\d)"), "")
        clean = clean.replace(Regex("(?:(?:20\\d{2})[-/年])?\\d{1,2}[-/月]\\d{1,2}[日号]?|今天|今日|今晚|明天|明日|后天|(下周|下星期|本周|这周|周|星期)[一二三四五六日天]"), "")
        clean = clean.replace(Regex("(凌晨|早上|上午|中午|下午|晚上)?\\s*(\\d{1,2}|[一二三四五六七八九十两]+)([:：]\\d{2}|点半?|时)"), "")
        clean = clean.replace(Regex("(?:预计|耗时|需要)\\s*[\\d.一二三四五六七八九十两]+\\s*(小时|分钟)"), "")
        clean = clean.replace(Regex("^(大家|请大家|请|同学们|完成|提交|上交|开始|举行|召开|参加|交|开)+"), "")
        clean = clean.substringBefore("截止").substringBefore("延期").substringBefore("改到").substringBefore("改为")
        clean = clean.replace(Regex("[，。,:：；;！!？?\\s至到~～—-]+"), " ").trim()
        clean = clean.removePrefix("前").removePrefix("之前").trim()
        return clean.take(120).ifBlank { "待确认事项" }
    }

    fun parse(input: Incoming, state: LocalState): Proposal {
        val text = input.content.trim()
        if (!NotificationMatcher.relevant(text)) return Proposal(Action.IGNORE, reasons = listOf("未发现明确的任务或日程关键词"))
        val reference = input.receivedAt.atZone(ZoneId.of(state.preferences.zone))
        val evidence = dates(text, reference)
        val notes = evidence.notes.toMutableList()
        val update = Regex("延期|改到|改为|提前|推迟|延长|调整到").containsMatchIn(text)
        val cancel = !update && Regex("取消|不用交|无需提交|不用提交").containsMatchIn(text)
        fun sameGroup(group: String, source: Source) = group == input.group && (source == input.source || source == Source.MANUAL || input.source == Source.MANUAL)
        fun matches(title: String): Boolean {
            val normalized = title.replace(Regex("^(完成|提交|上交)"), "").replace(" ", "")
            val lab = Regex("实验[一二三四五六七八九十\\d]+").find(normalized)?.value
            if (normalized != lab && normalized.length >= 2 && text.replace(" ", "").contains(normalized)) return true
            if (lab == null) return false
            return Regex("${Regex.escape(lab)}(?![一二三四五六七八九十\\d])").containsMatchIn(text)
        }
        val tasks = state.tasks.filter { it.status == TaskStatus.ACTIVE && sameGroup(it.group, it.source) && matches(it.title) }
        val events = state.events.filter { sameGroup(it.group, it.source) && matches(it.title) && it.end >= input.receivedAt.minusSeconds(86400) }
        val eventWords = Regex("考试|会议|开会|班会|上课|调课|讲座|答辩").containsMatchIn(text)
        val isEvent = events.isNotEmpty() && tasks.isEmpty() || eventWords && !Regex("作业|实验报告|提交|上交").containsMatchIn(text)
        val candidates = if (isEvent) events.map { it.id } else tasks.map { it.id }
        var action = when {
            cancel && isEvent -> Action.CANCEL_EVENT
            cancel -> Action.CANCEL_TASK
            update && isEvent -> Action.UPDATE_EVENT
            update -> Action.UPDATE_TASK
            isEvent -> Action.CREATE_EVENT
            else -> Action.CREATE_TASK
        }
        if (!update && !cancel && candidates.isNotEmpty()) {
            action = if (isEvent) Action.UPDATE_EVENT else Action.UPDATE_TASK
            notes += "已有相似事项，请确认是修改还是新建"
        }
        if (action.name.startsWith("UPDATE") || cancel) {
            if (candidates.size != 1) notes += if (candidates.isEmpty()) "未找到对应事项，请选择目标" else "匹配多个事项，请选择目标"
        }
        if (cancel) notes += "取消需要确认"
        val durationMatch = Regex("(?:预计|耗时|需要|用时)\\s*([\\d.]+|[一二三四五六七八九十两]+)\\s*(小时|分钟)").find(text)
        val amount = durationMatch?.groupValues?.get(1)?.let { it.toDoubleOrNull() ?: number(it)?.toDouble() }
        val minutes = amount?.let { if (durationMatch.groupValues[2] == "小时") (it * 60).toInt() else it.toInt() }?.takeIf { it in 1..20160 }
        var deadline: Instant? = null
        var start: Instant? = null
        var end: Instant? = null
        if (!cancel) {
            if (isEvent) {
                if (evidence.times.isEmpty()) notes += "日程缺少具体开始时间"
                if (evidence.date != null && evidence.times.isNotEmpty()) start = evidence.date.atTime(evidence.times.first()).atZone(reference.zone).toInstant()
                if (evidence.date != null && evidence.times.size >= 2) end = evidence.date.atTime(evidence.times.last()).atZone(reference.zone).toInstant()
                if (start != null && end == null && minutes != null) end = start.plusSeconds(minutes * 60L)
                if (end == null) notes += "日程缺少结束时间，请补充"
                if (start != null && end != null && end <= start) { notes += "结束时间不晚于开始，可能跨天，请核对"; end = null }
            } else {
                if (evidence.date != null && evidence.notes.none { it.startsWith("时间无效") }) {
                    deadline = evidence.date.atTime(evidence.times.lastOrNull() ?: LocalTime.of(23, 59)).atZone(reference.zone).toInstant()
                    if (evidence.times.isEmpty()) notes += "仅有日期，暂按当日 23:59 截止，请核对"
                }
                if (minutes == null && action == Action.CREATE_TASK) notes += "预计耗时默认 60 分钟，请核对"
                if (action == Action.CREATE_TASK && !Regex("截止|提交|上交|交作业|前交|前完成").containsMatchIn(text)) notes += "没有明确截止语义，请核对日期用途"
            }
        }
        val title = when {
            isEvent && events.size == 1 -> events.single().title
            !isEvent && tasks.size == 1 -> tasks.single().title
            else -> subject(text)
        }
        if (title == "待确认事项") notes += "请补充事项名称"
        if (Regex("另外|同时|以及|还有|分别|;|；|\\n").containsMatchIn(text)) notes += "可能包含多个事项，建议拆开录入"
        if (text.contains('…') || text.endsWith("...")) notes += "通知可能被截断，请补充完整内容"
        if ((deadline ?: start)?.isBefore(input.receivedAt) == true) notes += "识别的时间已过去"
        val autoSafe = action in listOf(Action.CREATE_TASK, Action.CREATE_EVENT) && notes.isEmpty() &&
            (if (isEvent) start != null && end != null else deadline != null && minutes != null)
        return Proposal(action, title, candidates.singleOrNull(), deadline, start, end, minutes, notes.distinct(), autoSafe)
    }
}
