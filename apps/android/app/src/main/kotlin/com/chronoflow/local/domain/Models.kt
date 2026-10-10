package com.chronoflow.local.domain

import java.time.Instant
import java.time.ZoneId
import java.util.UUID

fun newId(): String = UUID.randomUUID().toString()
enum class Source(val label: String, val packageName: String) {
    WECHAT("微信", "com.tencent.mm"), QQ("QQ", "com.tencent.mobileqq"), MANUAL("手动", "")
}
enum class Action(val label: String) {
    CREATE_TASK("创建任务"), UPDATE_TASK("修改任务"), CANCEL_TASK("取消任务"),
    CREATE_EVENT("创建日程"), UPDATE_EVENT("修改日程"), CANCEL_EVENT("取消日程"), IGNORE("忽略")
}
enum class NoticeStatus { REVIEW, APPLIED, IGNORED }
enum class TaskStatus { ACTIVE, COMPLETED, CANCELLED }
enum class AiReportType(val label: String) { DAILY("今日摘要"), RISK("风险预测"), WEEKLY("每周复盘") }
data class GroupRule(val source: Source, val name: String)
data class Preferences(
    val enabled: Boolean = false,
    val groups: List<GroupRule> = emptyList(),
    val autoCreate: Boolean = false,
    val startHour: Int = 8,
    val endHour: Int = 22,
    val zone: String = ZoneId.systemDefault().id,
    val reminders: Boolean = true,
    val aiEnabled: Boolean = false,
    val deepSeekApiKey: String = "",
    val deepSeekModel: String = "deepseek-flash",
    val accessibilityCaptureEnabled: Boolean = false,
)
data class Incoming(
    val source: Source, val group: String, val content: String, val receivedAt: Instant,
    val sender: String = "", val sourceKey: String = "",
)
data class Proposal(
    val action: Action, val title: String = "", val targetId: String? = null,
    val deadline: Instant? = null, val start: Instant? = null, val end: Instant? = null,
    val minutes: Int? = null, val reasons: List<String> = emptyList(), val autoSafe: Boolean = false,
    val confidence: Double? = null, val importance: Int = 3,
    val evidence: List<String> = emptyList(), val inferredFields: List<String> = emptyList(),
    val questions: List<String> = emptyList(), val subTasks: List<String> = emptyList(),
    val aiGenerated: Boolean = false, val changeSummary: String = "",
)
data class Notice(
    val id: String = newId(), val input: Incoming, val proposal: Proposal,
    val status: NoticeStatus = NoticeStatus.REVIEW, val appliedId: String? = null,
)
data class Task(
    val id: String = newId(), val title: String, val group: String = "", val source: Source = Source.MANUAL,
    val deadline: Instant? = null, val minutes: Int = 60, val remaining: Int = minutes,
    val priority: Int = 5, val splittable: Boolean = true, val status: TaskStatus = TaskStatus.ACTIVE,
    val deadlineLocked: Boolean = false, val sourceIds: List<String> = emptyList(),
    val subTasks: List<SubTask> = emptyList(), val actualMinutes: Int? = null,
    val completedAt: Instant? = null, val deadlineChanges: Int = 0,
)
data class SubTask(val id: String = newId(), val title: String, val done: Boolean = false)
data class FixedEvent(
    val id: String = newId(), val title: String, val start: Instant, val end: Instant,
    val group: String = "", val source: Source = Source.MANUAL, val sourceIds: List<String> = emptyList(),
)
data class Block(val id: String = newId(), val taskId: String, val start: Instant, val end: Instant, val locked: Boolean = false)
data class Risk(val title: String, val message: String, val missingMinutes: Int = 0)
data class Schedule(val version: Int = 0, val blocks: List<Block> = emptyList(), val risks: List<Risk> = emptyList(), val generatedAt: Instant? = null)
data class AiReport(
    val id: String = newId(), val type: AiReportType, val title: String,
    val summary: String, val bullets: List<String>, val generatedAt: Instant = Instant.now(),
)
data class LocalState(
    val preferences: Preferences = Preferences(), val notices: List<Notice> = emptyList(),
    val tasks: List<Task> = emptyList(), val events: List<FixedEvent> = emptyList(),
    val schedule: Schedule = Schedule(), val reminded: Set<String> = emptySet(),
    val aiReports: List<AiReport> = emptyList(),
)
