package com.chronoflow.local.model

import com.chronoflow.local.domain.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import android.content.Context
import java.time.Instant

/** Runs the APK's trained model and shared planner entirely on this phone. */
class ModelPlannerClient(private val context: Context) {
    private fun obj(vararg values: Pair<String, Any?>) = JSONObject().apply { values.forEach { (k,v) -> put(k,v ?: JSONObject.NULL) } }
    private fun arr(values: Iterable<*>) = JSONArray().apply { values.forEach { put(it) } }
    suspend fun plan(state: LocalState): Schedule = withContext(Dispatchers.IO) {
        val p = state.preferences
        require(p.localModelEnabled) { "请在设置中开启本机智能规划" }
        val active = state.tasks.filter { it.status == TaskStatus.ACTIVE && it.remaining > 0 }
        require(active.size <= 30) { "一次最多规划30项活动任务，请先归档已结束事项" }
        val body = obj("consent" to true, "timezone" to p.zone,
            "settings" to obj("startHour" to p.startHour, "endHour" to p.endHour, "dailyCapacityMinutes" to 360,
                "workloadPolicy" to "confirmed"),
            "tasks" to arr(active.map { t -> obj("id" to t.id,"title" to t.title,"category" to PersonalTimeModel.resolvedCategory(t).name,
                "course" to t.group.ifBlank { "unknown" },"difficulty" to t.difficulty,"priority" to t.priority,
                "minutes" to t.minutes,"remaining" to t.remaining,"releasedAt" to (t.releasedAt
                    ?: state.schedule.blocks.filter { it.taskId == t.id }.minOfOrNull { it.start }
                    ?: Instant.now()).toString(),
                "deadline" to t.deadline?.toString(),"splittable" to t.splittable) }),
            "events" to arr(state.events.filter { it.end > Instant.now() }.map { e -> obj("start" to e.start.toString(),"end" to e.end.toString()) }),
            "completedTasks" to arr(state.tasks.filter { it.status == TaskStatus.COMPLETED && (it.actualMinutes ?: 0) > 0 && it.completedAt != null }.takeLast(100).map { t ->
                obj("id" to t.id,"title" to t.title,"category" to PersonalTimeModel.resolvedCategory(t).name,"course" to t.group.ifBlank { "unknown" },
                    "minutes" to t.originalEstimateMinutes,"actualMinutes" to t.actualMinutes,"completedAt" to t.completedAt?.toString(),
                    "releasedAt" to t.releasedAt?.toString(),"deadline" to t.deadline?.toString(),"priority" to t.priority,"difficulty" to t.difficulty) }),
            "blocks" to arr(state.schedule.blocks.filter { it.end > Instant.now() }.map { b ->
                obj("taskId" to b.taskId,"start" to b.start.toString(),"end" to b.end.toString(),"locked" to b.locked) }),
            "history" to arr(state.executionHistory.takeLast(200).map { e -> obj("id" to e.id,"taskId" to e.taskId,
                "plannedStart" to e.plannedStart.toString(),"plannedMinutes" to e.plannedMinutes,
                "outcome" to e.outcome.name,"recordedAt" to e.recordedAt.toString()) }))
        val result = try { JSONObject(EmbeddedModelRuntime.plan(context, body.toString())) }
            catch (e: LinkageError) { error("手机无法加载内置模型运行库，请重新构建并安装应用") }
        require(result.getString("engine") == "chronoflow-local" && result.getBoolean("trained")) { "未获得本机训练模型结果" }
        val from = Instant.parse(result.getString("planningFrom"))
        val blocks = result.getJSONArray("blocks").let { a -> (0 until a.length()).map { i ->
            val b = a.getJSONObject(i)
            Block(taskId = b.getString("taskId"),start = Instant.parse(b.getString("start")),end = Instant.parse(b.getString("end")),locked = b.optBoolean("locked"))
        } }
        require(blocks.size <= 512 && blocks.all { b -> b.end > b.start && active.any { it.id == b.taskId } &&
            state.events.none { LocalScheduler.overlaps(b.start,b.end,it.start,it.end) } }) { "模型返回无效或冲突的时间块" }
        require(blocks.sortedBy { it.start }.zipWithNext().none { (a,b) -> a.end > b.start }) { "模型时间块互相重叠" }
        active.forEach { task ->
            val allocatedSeconds = blocks.filter { it.taskId == task.id }
                .sumOf { java.time.Duration.between(maxOf(it.start, from), it.end).seconds }
            val confirmedSeconds = ((task.remaining + 29) / 30) * 30L * 60
            require(allocatedSeconds <= confirmedSeconds) { "模型为「${task.title}」安排的时间超过剩余工时" }
        }
        val required = state.schedule.blocks.filter { b -> b.end > from && active.any { it.id == b.taskId } && (b.locked || b.start <= from) }
        require(required.all { a -> blocks.any { it.taskId == a.taskId && it.start == a.start && it.end == a.end } }) { "模型修改了锁定或正在执行的时间块" }
        val forecasts = result.getJSONArray("predictions").let { a -> (0 until a.length()).map { i ->
            val f = a.getJSONObject(i); TaskForecast(f.getString("taskId"),f.getInt("p50Minutes"),f.getInt("p80Minutes"),f.getInt("p95Minutes"))
        } }
        val risks = result.getJSONArray("risks").let { a -> (0 until a.length()).map { i ->
            val r = a.getJSONObject(i); Risk(r.getString("title"),r.getString("message"),r.getInt("missingMinutes"))
        } }
        Schedule(state.schedule.version + 1, (state.schedule.blocks.filter { it.end <= from && it.end > from.minusSeconds(30L * 86400) } + blocks).sortedBy { it.start },
            risks, Instant.parse(result.getString("generatedAt")), "chronoflow-local", forecasts)
    }
}
