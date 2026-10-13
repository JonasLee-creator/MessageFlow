package com.chronoflow.local

import com.chronoflow.local.domain.*
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId

/** Batch entry for the real LocalParser and UncertaintyEngine. No network calls. */
object EvaluationCli {
    private val zone: ZoneId = ZoneId.of("Asia/Shanghai")

    @JvmStatic
    fun main(args: Array<String>) {
        when (args.getOrNull(0)) {
            "rule" -> rule(Path.of(args[1]), Path.of(args[2]))
            "assess" -> assess(Path.of(args[1]), Path.of(args[2]))
            else -> error("usage: EvaluationCli rule|assess <input.jsonl> <output.jsonl>")
        }
    }

    private fun rule(input: Path, output: Path) {
        val lines = Files.readAllLines(input, StandardCharsets.UTF_8).filter { it.isNotBlank() }
        val out = lines.map { line ->
            val sample = Json.parse(line).obj()
            val started = System.nanoTime()
            val proposal = LocalParser.parse(incoming(sample), state(sample))
            val latency = (System.nanoTime() - started) / 1_000_000
            record("rule-only", sample, listOf(proposal), latency)
        }
        write(output, out)
    }

    private fun assess(input: Path, output: Path) {
        val lines = Files.readAllLines(input, StandardCharsets.UTF_8).filter { it.isNotBlank() }
        val out = lines.map { line ->
            val row = Json.parse(line).obj()
            val started = System.nanoTime()
            val incoming = incoming(row)
            val current = state(row)
            val baseline = LocalParser.parse(incoming, current)
            val proposals = row.list("items").map { item ->
                val proposal = proposal(item.obj())
                UncertaintyEngine.assess(incoming, proposal, current, baseline)
            }
            val latency = (System.nanoTime() - started) / 1_000_000
            record("full-system", row, proposals, latency)
        }
        write(output, out)
    }

    private fun record(system: String, sample: JsonObj, proposals: List<Proposal>, latency: Long): JsonObj {
        val items = proposals.map { it.toJson() }
        val ignore = items.isNotEmpty() && items.all { it.str("action") == "IGNORE" }
        return Json.obj(
            "sample_id" to Json.str(sample.str("sample_id").ifBlank { sample.str("id") }),
            "system" to Json.str(system),
            "run" to Json.num(1),
            "model" to Json.Null,
            "prediction" to Json.obj("items" to Json.arr(items), "should_ignore" to Json.bool(ignore)),
            "latency_ms" to Json.num(latency),
            "prompt_tokens" to Json.num(0),
            "completion_tokens" to Json.num(0),
            "http_status" to Json.Null,
            "retried" to Json.bool(false),
            "api_error" to Json.Null,
            "fallback_used" to Json.bool(false),
            "auto_apply" to Json.bool(proposals.any { it.autoSafe }),
        )
    }

    private fun Proposal.toJson(): JsonObj = Json.obj(
        "action" to Json.str(action.name),
        "title" to Json.str(title),
        "target_id" to (targetId?.let(Json::str) ?: Json.Null),
        "deadline" to instant(deadline),
        "start" to instant(start),
        "end" to instant(end),
        "minutes" to (minutes?.let { Json.num(it.toLong()) } ?: Json.Null),
        "evidence" to Json.arr(evidence.map(Json::str)),
        "questions" to Json.arr(questions.map(Json::str)),
    )

    private fun instant(value: Instant?): JsonVal = value?.atZone(zone)?.toOffsetDateTime()?.toString()?.let(Json::str) ?: Json.Null

    private fun incoming(sample: JsonObj): Incoming = Incoming(
        source = source(sample.str("source")),
        group = sample.obj("context").str("group"),
        content = sample.str("text"),
        receivedAt = OffsetDateTime.parse(sample.str("reference_time")).toInstant(),
    )

    private fun state(sample: JsonObj): LocalState {
        val context = sample.obj("context")
        val group = context.str("group")
        val source = source(sample.str("source"))
        val received = OffsetDateTime.parse(sample.str("reference_time")).toInstant()
        val tasks = mutableListOf<Task>()
        val events = mutableListOf<FixedEvent>()
        context.list("candidate_tasks").forEach { row ->
            val item = row.obj()
            val id = item.str("id")
            val title = item.str("title")
            if (id.startsWith("event-")) events += FixedEvent(id, title, received, received.plusSeconds(3600), group, source)
            else tasks += Task(id = id, title = title, group = group, source = source)
        }
        return LocalState(preferences = Preferences(zone = zone.id), tasks = tasks, events = events)
    }

    private fun proposal(item: JsonObj): Proposal {
        val action = runCatching { Action.valueOf(item.str("action")) }.getOrDefault(Action.IGNORE)
        return Proposal(
            action = action,
            title = item.str("title"),
            targetId = item.strOrNull("target_id"),
            deadline = item.instantOrNull("deadline"),
            start = item.instantOrNull("start"),
            end = item.instantOrNull("end"),
            minutes = item.intOrNull("minutes"),
            evidence = item.list("evidence").map { it.str() },
            questions = item.list("questions").map { it.str() },
            confidence = item.doubleOrNull("confidence"),
            inferredFields = item.list("inferred_fields").map { it.str() },
            aiGenerated = true,
        )
    }

    private fun source(name: String): Source = when (name) {
        "wechat" -> Source.WECHAT
        "qq" -> Source.QQ
        "canvas" -> Source.CANVAS
        else -> Source.MANUAL
    }

    private fun write(path: Path, rows: List<JsonObj>) {
        Files.createDirectories(path.parent)
        Files.write(path, rows.map { it.encode() }, StandardCharsets.UTF_8)
    }
}

private sealed interface JsonVal {
    fun encode(): String
    fun obj(): JsonObj = this as JsonObj
    fun list(): List<JsonVal> = (this as JsonArr).items
    fun str(): String = (this as JsonStr).value
}

private class JsonObj(val fields: Map<String, JsonVal>) : JsonVal {
    fun str(key: String): String = (fields[key] as? JsonStr)?.value ?: ""
    fun strOrNull(key: String): String? = (fields[key] as? JsonStr)?.value?.takeIf { it.isNotBlank() }
    fun obj(key: String): JsonObj = fields[key] as? JsonObj ?: Json.obj()
    fun list(key: String): List<JsonVal> = (fields[key] as? JsonArr)?.items ?: emptyList()
    fun intOrNull(key: String): Int? = (fields[key] as? JsonNum)?.value?.toInt()
    fun doubleOrNull(key: String): Double? = (fields[key] as? JsonNum)?.value
    fun instantOrNull(key: String): Instant? = strOrNull(key)?.let { runCatching { OffsetDateTime.parse(it).toInstant() }.getOrNull() }
    override fun encode(): String = fields.entries.joinToString(prefix = "{", postfix = "}") { (k, v) -> "${Json.quote(k)}:${v.encode()}" }
}

private class JsonArr(val items: List<JsonVal>) : JsonVal {
    override fun encode() = items.joinToString(prefix = "[", postfix = "]") { it.encode() }
}

private class JsonStr(val value: String) : JsonVal {
    override fun encode() = Json.quote(value)
}

private class JsonNum(val value: Double) : JsonVal {
    override fun encode(): String = if (value % 1.0 == 0.0) value.toLong().toString() else value.toString()
}

private class JsonBool(val value: Boolean) : JsonVal {
    override fun encode() = value.toString()
}

private object JsonNull : JsonVal {
    override fun encode() = "null"
}

private object Json {
    val Null: JsonVal = JsonNull
    fun str(value: String) = JsonStr(value)
    fun num(value: Long) = JsonNum(value.toDouble())
    fun bool(value: Boolean) = JsonBool(value)
    fun arr(items: Iterable<JsonVal>) = JsonArr(items.toList())
    fun obj(vararg pairs: Pair<String, JsonVal>) = JsonObj(linkedMapOf(*pairs))
    fun quote(value: String): String = buildString {
        append('"')
        value.forEach { ch ->
            when (ch) {
                '\\' -> append("\\\\")
                '"' -> append("\\\"")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> append(ch)
            }
        }
        append('"')
    }

    fun parse(text: String): JsonVal = Parser(text).parse()

    private class Parser(val text: String) {
        var i = 0
        fun parse(): JsonVal {
            val value = value()
            skip()
            return value
        }
        private fun value(): JsonVal {
            skip()
            return when (text[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> JsonStr(str())
                't' -> { i += 4; JsonBool(true) }
                'f' -> { i += 5; JsonBool(false) }
                'n' -> { i += 4; JsonNull }
                else -> num()
            }
        }
        private fun obj(): JsonObj {
            i++
            val fields = linkedMapOf<String, JsonVal>()
            skip()
            if (text[i] == '}') { i++; return JsonObj(fields) }
            while (true) {
                skip()
                val key = str()
                skip()
                check(text[i] == ':')
                i++
                fields[key] = value()
                skip()
                when (text[i]) {
                    ',' -> i++
                    '}' -> { i++; return JsonObj(fields) }
                    else -> error("json object")
                }
            }
        }
        private fun arr(): JsonArr {
            i++
            val items = mutableListOf<JsonVal>()
            skip()
            if (text[i] == ']') { i++; return JsonArr(items) }
            while (true) {
                items += value()
                skip()
                when (text[i]) {
                    ',' -> i++
                    ']' -> { i++; return JsonArr(items) }
                    else -> error("json array")
                }
            }
        }
        private fun str(): String {
            check(text[i] == '"')
            i++
            val out = StringBuilder()
            while (text[i] != '"') {
                if (text[i] == '\\') {
                    i++
                    out.append(when (val ch = text[i]) {
                        'n' -> '\n'
                        'r' -> '\r'
                        't' -> '\t'
                        'u' -> { val hex = text.substring(i + 1, i + 5); i += 4; hex.toInt(16).toChar() }
                        else -> ch
                    })
                } else out.append(text[i])
                i++
            }
            i++
            return out.toString()
        }
        private fun num(): JsonNum {
            val start = i
            if (text[i] == '-') i++
            while (i < text.length && text[i] in '0'..'9') i++
            if (i < text.length && text[i] == '.') { i++; while (i < text.length && text[i] in '0'..'9') i++ }
            return JsonNum(text.substring(start, i).toDouble())
        }
        private fun skip() { while (i < text.length && text[i].isWhitespace()) i++ }
    }
}
