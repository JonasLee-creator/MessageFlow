package com.chronoflow.local.domain

import java.time.Duration
import java.time.Instant

/** Local, deterministic learning and risk signals. DeepSeek adds semantic analysis on top. */
object IntelligenceEngine {
    private fun tokens(title: String): Set<String> {
        val compact = title.lowercase().replace(Regex("[^\\p{L}\\p{N}]+"), "")
        val words = title.lowercase().replace(Regex("[^\\p{L}\\p{N}]+"), " ").split(' ').filter { it.length >= 2 }
        return (words + compact.windowed(2)).toSet()
    }

    fun durationSuggestion(title: String, state: LocalState): Int? {
        val wanted = tokens(title)
        if (wanted.isEmpty()) return null
        val samples = state.tasks.filter { it.status == TaskStatus.COMPLETED && it.actualMinutes != null }
            .mapNotNull { task ->
                val overlap = tokens(task.title).intersect(wanted).size
                task.actualMinutes?.takeIf { overlap > 0 }?.let { overlap to it }
            }.sortedByDescending { it.first }.take(8).map { it.second }
        if (samples.isEmpty()) return null
        return samples.sorted()[samples.size / 2].coerceIn(1, 20160)
    }

    fun personalDurationSuggestion(task: Task, state: LocalState): DurationSuggestion? =
        PersonalTimeModel.durationSuggestion(task.title, task.group, task.category, task.difficulty,
            task.originalEstimateMinutes, state)

    fun risks(state: LocalState, now: Instant): List<Risk> {
        val learned = state.tasks.filter { it.status == TaskStatus.ACTIVE }.mapNotNull { task ->
            val insight = personalDurationSuggestion(task, state) ?: return@mapNotNull null
            if (insight.minutes > task.minutes * 5 / 4) Risk(task.title,
                "按历史实际用时，根据${insight.basis}通常需要预计值的 %.1f 倍，建议约 ${insight.minutes} 分钟；当前估计为 ${task.minutes} 分钟".format(insight.multiplier),
                insight.minutes - task.minutes) else null
        }
        val urgent = state.tasks.filter { task ->
            task.status == TaskStatus.ACTIVE && task.deadline?.let { it > now && Duration.between(now, it).toHours() <= 24 } == true
        }.mapNotNull { task ->
            val planned = state.schedule.blocks.filter { it.taskId == task.id && it.start >= now && (task.deadline == null || it.end <= task.deadline) }
                .sumOf { Duration.between(it.start, it.end).toMinutes().toInt() }
            if (planned < task.remaining) Risk(task.title, "24 小时内截止，仍有 ${task.remaining - planned} 分钟没有可用安排", task.remaining - planned) else null
        }
        val repeated = state.tasks.filter { it.status == TaskStatus.ACTIVE && it.deadlineChanges >= 2 }
            .map { Risk(it.title, "截止时间已经变更 ${it.deadlineChanges} 次，建议重新确认要求") }
        return (state.schedule.risks + learned + urgent + repeated).distinctBy { it.title to it.message }
    }
}
