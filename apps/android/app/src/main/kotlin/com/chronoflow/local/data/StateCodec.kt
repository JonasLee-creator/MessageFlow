package com.chronoflow.local.data

import com.chronoflow.local.domain.*
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/** Explicit schema, no reflection or downloaded serialization/codegen plugin. */
object StateCodec {
    private fun obj(vararg fields: Pair<String, Any?>) = JSONObject().apply { fields.forEach { (k, v) -> put(k, v ?: JSONObject.NULL) } }
    private fun arr(values: Iterable<*>) = JSONArray().apply { values.forEach { put(it) } }
    private fun JSONObject.stringOrNull(key: String): String? = if (has(key) && !isNull(key)) getString(key) else null
    private fun JSONObject.instant(key: String): Instant? = stringOrNull(key)?.let(Instant::parse)
    private fun JSONObject.rows(key: String): List<JSONObject> = optJSONArray(key)?.let { a -> (0 until a.length()).map { a.getJSONObject(it) } } ?: emptyList()
    private fun JSONObject.strings(key: String): List<String> = optJSONArray(key)?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()

    fun encode(state: LocalState): ByteArray {
        val p = state.preferences
        return obj("schema" to 3, "preferences" to obj("enabled" to p.enabled, "autoCreate" to p.autoCreate,
            "startHour" to p.startHour, "endHour" to p.endHour, "zone" to p.zone, "reminders" to p.reminders,
            "aiEnabled" to p.aiEnabled, "deepSeekApiKey" to p.deepSeekApiKey, "deepSeekModel" to p.deepSeekModel,
            "aiApiMode" to p.aiApiMode.name, "aiBaseUrl" to p.aiBaseUrl,
            "officialGatewayUrl" to p.officialGatewayUrl, "officialAccessCode" to p.officialAccessCode,
            "canvasEnabled" to p.canvasEnabled, "canvasBaseUrl" to p.canvasBaseUrl, "canvasAccessToken" to p.canvasAccessToken,
            "groups" to arr(p.groups.map { obj("source" to it.source.name, "name" to it.name) })),
            "notices" to arr(state.notices.map { n -> obj("id" to n.id, "status" to n.status.name, "appliedId" to n.appliedId,
                "input" to obj("source" to n.input.source.name, "group" to n.input.group, "content" to n.input.content, "receivedAt" to n.input.receivedAt.toString(), "sender" to n.input.sender, "sourceKey" to n.input.sourceKey),
                "proposal" to proposal(n.proposal)) }),
            "tasks" to arr(state.tasks.map { t -> obj("id" to t.id, "title" to t.title, "group" to t.group, "source" to t.source.name,
                "deadline" to t.deadline?.toString(), "minutes" to t.minutes, "remaining" to t.remaining, "priority" to t.priority,
                "splittable" to t.splittable, "status" to t.status.name, "deadlineLocked" to t.deadlineLocked, "sourceIds" to arr(t.sourceIds),
                "subTasks" to arr(t.subTasks.map { s -> obj("id" to s.id, "title" to s.title, "done" to s.done) }),
                "actualMinutes" to t.actualMinutes, "completedAt" to t.completedAt?.toString(), "deadlineChanges" to t.deadlineChanges,
                "category" to t.category.name, "difficulty" to t.difficulty, "originalEstimateMinutes" to t.originalEstimateMinutes) }),
            "events" to arr(state.events.map { e -> obj("id" to e.id, "title" to e.title, "start" to e.start.toString(), "end" to e.end.toString(), "group" to e.group, "source" to e.source.name, "sourceIds" to arr(e.sourceIds)) }),
            "schedule" to obj("version" to state.schedule.version, "generatedAt" to state.schedule.generatedAt?.toString(),
                "blocks" to arr(state.schedule.blocks.map { b -> obj("id" to b.id, "taskId" to b.taskId, "start" to b.start.toString(), "end" to b.end.toString(), "locked" to b.locked) }),
                "risks" to arr(state.schedule.risks.map { r -> obj("title" to r.title, "message" to r.message, "missingMinutes" to r.missingMinutes) })),
            "reminded" to arr(state.reminded),
            "aiReports" to arr(state.aiReports.map { r -> obj("id" to r.id, "type" to r.type.name, "title" to r.title,
                "summary" to r.summary, "bullets" to arr(r.bullets), "generatedAt" to r.generatedAt.toString()) }),
            "executionHistory" to arr(state.executionHistory.map { e -> obj("id" to e.id, "taskId" to e.taskId,
                "category" to e.category.name, "group" to e.group, "plannedStart" to e.plannedStart.toString(),
                "plannedMinutes" to e.plannedMinutes, "actualMinutes" to e.actualMinutes, "outcome" to e.outcome.name,
                "recordedAt" to e.recordedAt.toString()) })).toString().toByteArray(Charsets.UTF_8)
    }

    private fun proposal(p: Proposal) = obj("action" to p.action.name, "title" to p.title, "targetId" to p.targetId,
        "deadline" to p.deadline?.toString(), "start" to p.start?.toString(), "end" to p.end?.toString(),
        "minutes" to p.minutes, "reasons" to arr(p.reasons), "autoSafe" to p.autoSafe,
        "confidence" to p.confidence, "importance" to p.importance, "evidence" to arr(p.evidence),
        "inferredFields" to arr(p.inferredFields), "questions" to arr(p.questions), "subTasks" to arr(p.subTasks),
        "aiGenerated" to p.aiGenerated, "changeSummary" to p.changeSummary,
        "uncertainty" to p.uncertainty?.let { u -> obj("overall" to u.overall,
            "blockingFields" to arr(u.blockingFields), "questions" to arr(u.questions), "mayAutoCreate" to u.mayAutoCreate,
            "fields" to obj("action" to u.fields.action, "title" to u.fields.title, "time" to u.fields.time,
                "target" to u.fields.target, "evidence" to u.fields.evidence)) })

    fun decode(bytes: ByteArray): LocalState {
        val root = JSONObject(String(bytes, Charsets.UTF_8))
        require(root.getInt("schema") in 1..3) { "本地数据版本不受支持" }
        val p = root.getJSONObject("preferences")
        val preferences = Preferences(p.getBoolean("enabled"), p.rows("groups").map { GroupRule(Source.valueOf(it.getString("source")), it.getString("name")) },
            p.optBoolean("autoCreate"), p.getInt("startHour"), p.getInt("endHour"), p.getString("zone"), p.optBoolean("reminders", true),
            p.optBoolean("aiEnabled"), p.optString("deepSeekApiKey"), p.optString("deepSeekModel", "deepseek-flash"),
            p.optBoolean("canvasEnabled"), p.optString("canvasBaseUrl"), p.optString("canvasAccessToken"),
            aiApiMode = if (p.has("aiApiMode")) ApiMode.valueOf(p.getString("aiApiMode")) else ApiMode.USER,
            aiBaseUrl = p.optString("aiBaseUrl", "https://api.deepseek.com"),
            officialGatewayUrl = p.optString("officialGatewayUrl"), officialAccessCode = p.optString("officialAccessCode"))
        val notices = root.rows("notices").map { n ->
            val i = n.getJSONObject("input"); val q = n.getJSONObject("proposal")
            val uncertainty = q.optJSONObject("uncertainty")?.let { u ->
                val f = u.getJSONObject("fields")
                UncertaintyAssessment(FieldConfidence(f.getDouble("action"), f.getDouble("title"), f.getDouble("time"),
                    f.getDouble("target"), f.getDouble("evidence")), u.getDouble("overall"), u.strings("blockingFields"),
                    u.strings("questions"), u.optBoolean("mayAutoCreate"))
            }
            Notice(n.getString("id"), Incoming(Source.valueOf(i.getString("source")), i.getString("group"), i.getString("content"), Instant.parse(i.getString("receivedAt")), i.optString("sender"), i.optString("sourceKey")),
                Proposal(action = Action.valueOf(q.getString("action")), title = q.getString("title"), targetId = q.stringOrNull("targetId"),
                    deadline = q.instant("deadline"), start = q.instant("start"), end = q.instant("end"),
                    minutes = if (q.isNull("minutes")) null else q.getInt("minutes"), reasons = q.strings("reasons"), autoSafe = q.optBoolean("autoSafe"),
                    confidence = if (q.has("confidence") && !q.isNull("confidence")) q.getDouble("confidence") else null,
                    importance = q.optInt("importance", 3), evidence = q.strings("evidence"), inferredFields = q.strings("inferredFields"),
                    questions = q.strings("questions"), subTasks = q.strings("subTasks"), aiGenerated = q.optBoolean("aiGenerated"),
                    changeSummary = q.optString("changeSummary"), uncertainty = uncertainty),
                NoticeStatus.valueOf(n.getString("status")), n.stringOrNull("appliedId"))
        }
        val tasks = root.rows("tasks").map { t -> Task(id = t.getString("id"), title = t.getString("title"), group = t.getString("group"),
            source = Source.valueOf(t.getString("source")), deadline = t.instant("deadline"), minutes = t.getInt("minutes"), remaining = t.getInt("remaining"),
            priority = t.getInt("priority"), splittable = t.getBoolean("splittable"), status = TaskStatus.valueOf(t.getString("status")),
            deadlineLocked = t.optBoolean("deadlineLocked"), sourceIds = t.strings("sourceIds"),
            subTasks = t.rows("subTasks").map { s -> SubTask(s.optString("id", newId()), s.getString("title"), s.optBoolean("done")) },
            actualMinutes = if (t.has("actualMinutes") && !t.isNull("actualMinutes")) t.getInt("actualMinutes") else null,
            completedAt = t.instant("completedAt"), deadlineChanges = t.optInt("deadlineChanges"),
            category = runCatching { TaskCategory.valueOf(t.optString("category", TaskCategory.AUTO.name)) }.getOrDefault(TaskCategory.AUTO),
            difficulty = t.optInt("difficulty", 3).coerceIn(1, 5), originalEstimateMinutes = t.optInt("originalEstimateMinutes", t.getInt("minutes"))) }
        val events = root.rows("events").map { e -> FixedEvent(e.getString("id"), e.getString("title"), Instant.parse(e.getString("start")), Instant.parse(e.getString("end")), e.getString("group"), Source.valueOf(e.getString("source")), e.strings("sourceIds")) }
        val s = root.getJSONObject("schedule")
        val schedule = Schedule(s.getInt("version"), s.rows("blocks").map { b -> Block(b.getString("id"), b.getString("taskId"), Instant.parse(b.getString("start")), Instant.parse(b.getString("end")), b.getBoolean("locked")) },
            s.rows("risks").map { r -> Risk(r.getString("title"), r.getString("message"), r.getInt("missingMinutes")) }, s.instant("generatedAt"))
        val reports = root.rows("aiReports").map { r -> AiReport(r.getString("id"), AiReportType.valueOf(r.getString("type")),
            r.getString("title"), r.getString("summary"), r.strings("bullets"), Instant.parse(r.getString("generatedAt"))) }
        val history = root.rows("executionHistory").map { e -> ExecutionRecord(e.getString("id"), e.getString("taskId"),
            TaskCategory.valueOf(e.getString("category")), e.optString("group"), Instant.parse(e.getString("plannedStart")),
            e.getInt("plannedMinutes"), if (e.has("actualMinutes") && !e.isNull("actualMinutes")) e.getInt("actualMinutes") else null,
            ExecutionOutcome.valueOf(e.getString("outcome")), Instant.parse(e.getString("recordedAt"))) }
        return LocalState(preferences, notices, tasks, events, schedule, root.strings("reminded").toSet(), reports, history)
    }
}
