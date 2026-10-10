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
        return obj("schema" to 1, "preferences" to obj("enabled" to p.enabled, "autoCreate" to p.autoCreate,
            "startHour" to p.startHour, "endHour" to p.endHour, "zone" to p.zone, "reminders" to p.reminders,
            "aiEnabled" to p.aiEnabled, "deepSeekApiKey" to p.deepSeekApiKey, "deepSeekModel" to p.deepSeekModel,
            "canvasEnabled" to p.canvasEnabled, "canvasBaseUrl" to p.canvasBaseUrl, "canvasAccessToken" to p.canvasAccessToken,
            "groups" to arr(p.groups.map { obj("source" to it.source.name, "name" to it.name) })),
            "notices" to arr(state.notices.map { n -> obj("id" to n.id, "status" to n.status.name, "appliedId" to n.appliedId,
                "input" to obj("source" to n.input.source.name, "group" to n.input.group, "content" to n.input.content, "receivedAt" to n.input.receivedAt.toString(), "sender" to n.input.sender, "sourceKey" to n.input.sourceKey),
                "proposal" to proposal(n.proposal)) }),
            "tasks" to arr(state.tasks.map { t -> obj("id" to t.id, "title" to t.title, "group" to t.group, "source" to t.source.name,
                "deadline" to t.deadline?.toString(), "minutes" to t.minutes, "remaining" to t.remaining, "priority" to t.priority,
                "splittable" to t.splittable, "status" to t.status.name, "deadlineLocked" to t.deadlineLocked, "sourceIds" to arr(t.sourceIds),
                "subTasks" to arr(t.subTasks.map { s -> obj("id" to s.id, "title" to s.title, "done" to s.done) }),
                "actualMinutes" to t.actualMinutes, "completedAt" to t.completedAt?.toString(), "deadlineChanges" to t.deadlineChanges) }),
            "events" to arr(state.events.map { e -> obj("id" to e.id, "title" to e.title, "start" to e.start.toString(), "end" to e.end.toString(), "group" to e.group, "source" to e.source.name, "sourceIds" to arr(e.sourceIds)) }),
            "schedule" to obj("version" to state.schedule.version, "generatedAt" to state.schedule.generatedAt?.toString(),
                "blocks" to arr(state.schedule.blocks.map { b -> obj("id" to b.id, "taskId" to b.taskId, "start" to b.start.toString(), "end" to b.end.toString(), "locked" to b.locked) }),
                "risks" to arr(state.schedule.risks.map { r -> obj("title" to r.title, "message" to r.message, "missingMinutes" to r.missingMinutes) })),
            "reminded" to arr(state.reminded),
            "aiReports" to arr(state.aiReports.map { r -> obj("id" to r.id, "type" to r.type.name, "title" to r.title,
                "summary" to r.summary, "bullets" to arr(r.bullets), "generatedAt" to r.generatedAt.toString()) })).toString().toByteArray(Charsets.UTF_8)
    }

    private fun proposal(p: Proposal) = obj("action" to p.action.name, "title" to p.title, "targetId" to p.targetId,
        "deadline" to p.deadline?.toString(), "start" to p.start?.toString(), "end" to p.end?.toString(),
        "minutes" to p.minutes, "reasons" to arr(p.reasons), "autoSafe" to p.autoSafe,
        "confidence" to p.confidence, "importance" to p.importance, "evidence" to arr(p.evidence),
        "inferredFields" to arr(p.inferredFields), "questions" to arr(p.questions), "subTasks" to arr(p.subTasks),
        "aiGenerated" to p.aiGenerated, "changeSummary" to p.changeSummary)

    fun decode(bytes: ByteArray): LocalState {
        val root = JSONObject(String(bytes, Charsets.UTF_8))
        require(root.getInt("schema") == 1) { "本地数据版本不受支持" }
        val p = root.getJSONObject("preferences")
        val preferences = Preferences(p.getBoolean("enabled"), p.rows("groups").map { GroupRule(Source.valueOf(it.getString("source")), it.getString("name")) },
            p.optBoolean("autoCreate"), p.getInt("startHour"), p.getInt("endHour"), p.getString("zone"), p.optBoolean("reminders", true),
            p.optBoolean("aiEnabled"), p.optString("deepSeekApiKey"), p.optString("deepSeekModel", "deepseek-flash"),
            p.optBoolean("canvasEnabled"), p.optString("canvasBaseUrl"), p.optString("canvasAccessToken"))
        val notices = root.rows("notices").map { n ->
            val i = n.getJSONObject("input"); val q = n.getJSONObject("proposal")
            Notice(n.getString("id"), Incoming(Source.valueOf(i.getString("source")), i.getString("group"), i.getString("content"), Instant.parse(i.getString("receivedAt")), i.optString("sender"), i.optString("sourceKey")),
                Proposal(Action.valueOf(q.getString("action")), q.getString("title"), q.stringOrNull("targetId"), q.instant("deadline"), q.instant("start"), q.instant("end"), if (q.isNull("minutes")) null else q.getInt("minutes"), q.strings("reasons"), q.optBoolean("autoSafe"),
                    if (q.has("confidence") && !q.isNull("confidence")) q.getDouble("confidence") else null, q.optInt("importance", 3),
                    q.strings("evidence"), q.strings("inferredFields"), q.strings("questions"), q.strings("subTasks"),
                    q.optBoolean("aiGenerated"), q.optString("changeSummary")),
                NoticeStatus.valueOf(n.getString("status")), n.stringOrNull("appliedId"))
        }
        val tasks = root.rows("tasks").map { t -> Task(t.getString("id"), t.getString("title"), t.getString("group"), Source.valueOf(t.getString("source")), t.instant("deadline"),
            t.getInt("minutes"), t.getInt("remaining"), t.getInt("priority"), t.getBoolean("splittable"), TaskStatus.valueOf(t.getString("status")), t.optBoolean("deadlineLocked"), t.strings("sourceIds"),
            t.rows("subTasks").map { s -> SubTask(s.optString("id", newId()), s.getString("title"), s.optBoolean("done")) },
            if (t.has("actualMinutes") && !t.isNull("actualMinutes")) t.getInt("actualMinutes") else null, t.instant("completedAt"), t.optInt("deadlineChanges")) }
        val events = root.rows("events").map { e -> FixedEvent(e.getString("id"), e.getString("title"), Instant.parse(e.getString("start")), Instant.parse(e.getString("end")), e.getString("group"), Source.valueOf(e.getString("source")), e.strings("sourceIds")) }
        val s = root.getJSONObject("schedule")
        val schedule = Schedule(s.getInt("version"), s.rows("blocks").map { b -> Block(b.getString("id"), b.getString("taskId"), Instant.parse(b.getString("start")), Instant.parse(b.getString("end")), b.getBoolean("locked")) },
            s.rows("risks").map { r -> Risk(r.getString("title"), r.getString("message"), r.getInt("missingMinutes")) }, s.instant("generatedAt"))
        val reports = root.rows("aiReports").map { r -> AiReport(r.getString("id"), AiReportType.valueOf(r.getString("type")),
            r.getString("title"), r.getString("summary"), r.strings("bullets"), Instant.parse(r.getString("generatedAt"))) }
        return LocalState(preferences, notices, tasks, events, schedule, root.strings("reminded").toSet(), reports)
    }
}
