package com.chronoflow.local.domain

import java.time.Instant

enum class CanvasItemType { ASSIGNMENT, ANNOUNCEMENT, EVENT }

data class CanvasItem(
    val key: String,
    val type: CanvasItemType,
    val courseName: String,
    val title: String,
    val body: String = "",
    val dueAt: Instant? = null,
    val startAt: Instant? = null,
    val endAt: Instant? = null,
    val htmlUrl: String = "",
    val updatedAt: Instant? = null,
)

data class CanvasMergeStats(val added: Int = 0, val updated: Int = 0, val unchanged: Int = 0)
data class CanvasMergeResult(val state: LocalState, val stats: CanvasMergeStats)

/** Converts trusted, structured Canvas API records into the same review flow as chat notifications. */
object CanvasSyncEngine {
    fun merge(state: LocalState, items: List<CanvasItem>, now: Instant): CanvasMergeResult {
        var current = state
        var added = 0
        var updated = 0
        var unchanged = 0
        items.distinctBy { it.key }.forEach { item ->
            require(item.key.isNotBlank() && item.key.length <= 300)
            val sourceKey = "canvas:${item.key}"
            val previous = current.notices.firstOrNull { it.input.sourceKey == sourceKey }
            val input = Incoming(
                source = Source.CANVAS,
                group = item.courseName.take(100).ifBlank { "Canvas 课程" },
                content = content(item).take(10000),
                receivedAt = item.updatedAt ?: now,
                sender = "Canvas",
                sourceKey = sourceKey,
            )
            if (previous?.input?.content == input.content) {
                unchanged++
                return@forEach
            }
            val targetId = current.notices.firstOrNull {
                it.input.sourceKey == sourceKey && it.status == NoticeStatus.APPLIED && it.appliedId != null
            }?.appliedId
            val proposal = UncertaintyEngine.assess(input, proposal(item, input, current, targetId, previous != null), current)
            val replacement = Notice(
                id = if (previous?.status == NoticeStatus.REVIEW) previous.id else newId(),
                input = input,
                proposal = proposal,
                status = if (proposal.action == Action.IGNORE) NoticeStatus.IGNORED else NoticeStatus.REVIEW,
            )
            current = if (previous?.status == NoticeStatus.REVIEW) {
                current.copy(notices = current.notices.map { if (it.id == previous.id) replacement else it })
            } else {
                current.copy(notices = (listOf(replacement) + current.notices).take(1000))
            }
            if (previous == null) added++ else updated++
        }
        return CanvasMergeResult(current, CanvasMergeStats(added, updated, unchanged))
    }

    private fun proposal(item: CanvasItem, input: Incoming, state: LocalState, targetId: String?, changed: Boolean): Proposal {
        val title = item.title.trim().take(200).ifBlank { "Canvas 待确认事项" }
        val evidence = listOf("Canvas 官方 API：$title")
        val change = if (changed) "Canvas 中的时间或内容已更新，请核对" else "从 Canvas 导入的新事项"
        return when (item.type) {
            CanvasItemType.ASSIGNMENT -> {
                val activeTarget = targetId?.let { id -> state.tasks.firstOrNull { it.id == id && it.status == TaskStatus.ACTIVE } }
                if (targetId != null && activeTarget == null) {
                    Proposal(Action.IGNORE, title, reasons = listOf("对应任务已完成或取消，保留此次 Canvas 更新供查阅"),
                        evidence = evidence, importance = 4, changeSummary = change)
                } else Proposal(
                    action = if (activeTarget == null) Action.CREATE_TASK else Action.UPDATE_TASK,
                    title = title,
                    targetId = activeTarget?.id,
                    deadline = item.dueAt,
                    minutes = activeTarget?.minutes ?: 60,
                    reasons = buildList {
                        if (item.dueAt == null) add("Canvas 未提供截止时间，请核对")
                        if (activeTarget == null) add("预计耗时默认 60 分钟，请核对")
                    },
                    autoSafe = false,
                    importance = if (item.dueAt == null) 3 else 4,
                    evidence = evidence,
                    inferredFields = listOf("预计耗时 60 分钟").takeIf { activeTarget == null }.orEmpty(),
                    changeSummary = change,
                )
            }
            CanvasItemType.EVENT -> {
                val existing = targetId?.let { id -> state.events.firstOrNull { it.id == id } }
                val inferredEnd = item.startAt != null && item.endAt == null
                Proposal(
                    action = if (existing == null) Action.CREATE_EVENT else Action.UPDATE_EVENT,
                    title = title,
                    targetId = existing?.id,
                    start = item.startAt,
                    end = item.endAt ?: item.startAt?.plusSeconds(3600),
                    reasons = buildList {
                        if (item.startAt == null) add("Canvas 未提供开始时间，请补充")
                        if (inferredEnd) add("Canvas 未提供结束时间，暂按 1 小时，请核对")
                    },
                    autoSafe = false,
                    importance = 4,
                    evidence = evidence,
                    inferredFields = if (inferredEnd) listOf("结束时间按开始后 1 小时估计") else emptyList(),
                    changeSummary = change,
                )
            }
            CanvasItemType.ANNOUNCEMENT -> LocalParser.parse(input, state).copy(
                evidence = evidence,
                autoSafe = false,
                changeSummary = change,
            )
        }
    }

    private fun content(item: CanvasItem): String = buildString {
        append(when (item.type) {
            CanvasItemType.ASSIGNMENT -> "Canvas 作业"
            CanvasItemType.ANNOUNCEMENT -> "Canvas 公告"
            CanvasItemType.EVENT -> "Canvas 日历"
        })
        append("：").append(item.title.trim())
        append("\n课程：").append(item.courseName.trim())
        item.dueAt?.let { append("\n截止：").append(it) }
        item.startAt?.let { append("\n开始：").append(it) }
        item.endAt?.let { append("\n结束：").append(it) }
        if (item.body.isNotBlank()) append("\n说明：").append(item.body.trim())
        if (item.htmlUrl.isNotBlank()) append("\n链接：").append(item.htmlUrl.trim())
    }
}
