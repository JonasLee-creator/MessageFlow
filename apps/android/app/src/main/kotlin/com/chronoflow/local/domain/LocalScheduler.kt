package com.chronoflow.local.domain

import java.time.*
import kotlin.math.ceil

/** Earliest-deadline-first heuristic, not an optimality/feasibility proof. */
object LocalScheduler {
    private const val STEP = 30L * 60
    fun overlaps(a: Instant, b: Instant, c: Instant, d: Instant): Boolean = a < d && c < b
    fun plan(state: LocalState, now: Instant): Schedule {
        val prefs = state.preferences
        require(prefs.startHour in 0..23 && prefs.endHour in 1..24 && prefs.endHour > prefs.startHour)
        val zone = ZoneId.of(prefs.zone)
        val active = state.tasks.filter { it.status == TaskStatus.ACTIVE }
        val activeIds = active.map { it.id }.toSet()
        val past = state.schedule.blocks.filter { it.end <= now && it.end > now.minusSeconds(30L * 86400) }
        val preserved = state.schedule.blocks.filter { it.taskId in activeIds && it.end > now && (it.locked || it.start <= now) }
        val result = preserved.toMutableList()
        val risks = mutableListOf<Risk>()
        for (block in preserved) {
            val task = active.first { it.id == block.taskId }
            if (task.deadline != null && block.end > task.deadline) risks += Risk(task.title, "锁定或进行中的时间超过截止时间")
            if (state.events.any { overlaps(block.start, block.end, it.start, it.end) }) risks += Risk(task.title, "锁定或进行中的安排与固定日程冲突")
        }
        preserved.forEachIndexed { index, a ->
            if (preserved.drop(index + 1).any { overlaps(a.start, a.end, it.start, it.end) }) risks += Risk("锁定安排", "已有锁定或进行中的时间互相冲突")
        }
        state.events.sortedBy { it.start }.forEachIndexed { index, a ->
            if (state.events.sortedBy { it.start }.drop(index + 1).any { it.end > now && overlaps(a.start, a.end, it.start, it.end) }) risks += Risk(a.title, "固定日程互相重叠，请手动调整")
        }
        val slots = mutableListOf<Instant>()
        val firstDay = now.atZone(zone).toLocalDate()
        for (day in 0L until 14L) {
            val date = firstDay.plusDays(day)
            var slot = date.atTime(prefs.startHour, 0).atZone(zone).toInstant()
            val end = if (prefs.endHour == 24) date.plusDays(1).atStartOfDay(zone).toInstant() else date.atTime(prefs.endHour, 0).atZone(zone).toInstant()
            while (slot.plusSeconds(STEP) <= end) {
                if (slot >= now && state.events.none { overlaps(slot, slot.plusSeconds(STEP), it.start, it.end) } && preserved.none { overlaps(slot, slot.plusSeconds(STEP), it.start, it.end) }) slots += slot
                slot = slot.plusSeconds(STEP)
            }
        }
        val available = slots.toMutableSet()
        for (task in active.sortedWith(compareBy<Task> { it.deadline ?: Instant.MAX }.thenByDescending { it.priority }.thenBy { it.id })) {
            val reserved = preserved.filter { it.taskId == task.id }.sumOf { Duration.between(maxOf(it.start, now), it.end).seconds / 60.0 }
            val needed = ceil((task.remaining - reserved).coerceAtLeast(0.0) / 30).toInt()
            if (needed == 0) continue
            if (!task.splittable && reserved > 0) {
                risks += Risk(task.title, "不可拆分任务已有锁定段，请先解锁再调整完整时长", needed * 30)
                continue
            }
            val eligible = slots.filter { it in available && (task.deadline == null || it.plusSeconds(STEP) <= task.deadline) }
            val chosen = if (task.splittable) eligible.take(needed) else {
                val set = eligible.toSet()
                val start = eligible.firstOrNull { candidate -> (0 until needed).all { candidate.plusSeconds(STEP * it) in set } }
                if (start == null) emptyList() else (0 until needed).map { start.plusSeconds(STEP * it) }
            }
            if (chosen.size < needed) risks += Risk(task.title,
                if (task.splittable) "本轮排程未找到足够的截止前空闲时间，可调整期限、耗时或时间偏好" else "本轮排程未找到足够长的连续时段", (needed - chosen.size) * 30)
            var runStart: Instant? = null
            var runEnd: Instant? = null
            for (slot in chosen) {
                available.remove(slot)
                if (runEnd != slot) {
                    if (runStart != null && runEnd != null) result += Block(taskId = task.id, start = runStart, end = runEnd)
                    runStart = slot
                }
                runEnd = slot.plusSeconds(STEP)
            }
            if (runStart != null && runEnd != null) result += Block(taskId = task.id, start = runStart, end = runEnd)
        }
        return Schedule(state.schedule.version + 1, (past + result).sortedBy { it.start }, risks.distinct(), now)
    }
}
