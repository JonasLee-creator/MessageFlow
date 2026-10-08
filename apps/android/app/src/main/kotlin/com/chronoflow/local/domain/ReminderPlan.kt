package com.chronoflow.local.domain

import java.time.Instant

data class ReminderItem(val key: String, val title: String, val start: Instant, val end: Instant)
object ReminderPlan {
    fun pending(state: LocalState, now: Instant): List<ReminderItem> {
        if (!state.preferences.reminders) return emptyList()
        val blocks = state.schedule.blocks.mapNotNull { b ->
            val task = state.tasks.firstOrNull { it.id == b.taskId && it.status == TaskStatus.ACTIVE } ?: return@mapNotNull null
            // Semantic identity survives a replan that recreates an equivalent block.
            ReminderItem("task:${task.id}:${b.start}", task.title, b.start, b.end)
        }
        val events = state.events.map { ReminderItem("event:${it.id}:${it.start}", it.title, it.start, it.end) }
        return (blocks + events).filter { it.key !in state.reminded && it.end > now && it.start >= now.minusSeconds(900) }.sortedBy { it.start }
    }
}
