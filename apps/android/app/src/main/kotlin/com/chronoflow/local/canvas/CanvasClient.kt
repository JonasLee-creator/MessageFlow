package com.chronoflow.local.canvas

import com.chronoflow.local.domain.CanvasItem
import com.chronoflow.local.domain.CanvasItemType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.Instant
import java.time.temporal.ChronoUnit

data class CanvasSyncPayload(val courseCount: Int, val items: List<CanvasItem>)

/** Small Canvas LMS REST client. The bearer token is never put in URLs or logs. */
class CanvasClient {
    suspend fun sync(baseUrl: String, accessToken: String, now: Instant = Instant.now()): CanvasSyncPayload = withContext(Dispatchers.IO) {
        val base = normalizeBaseUrl(baseUrl)
        validateToken(accessToken)
        val courses = pages(base, accessToken, "/api/v1/courses", listOf("enrollment_state" to "active", "per_page" to "100"))
            .flatMap(::objects)
            .mapNotNull { row ->
                val id = row.text("id") ?: return@mapNotNull null
                val name = row.text("name") ?: row.text("course_code") ?: "Canvas 课程 $id"
                Course(id, name.take(100))
            }
            .distinctBy { it.id }
            .take(200)
        val names = courses.associate { "course_${it.id}" to it.name }
        val assignments = courses.flatMap { course ->
            pages(base, accessToken, "/api/v1/courses/${encode(course.id)}/assignments", listOf("order_by" to "due_at", "per_page" to "100"))
                .flatMap(::objects)
                .mapNotNull { assignment(it, course) }
        }
        val range = listOf(
            "start_date" to now.minus(30, ChronoUnit.DAYS).toString(),
            "end_date" to now.plus(365, ChronoUnit.DAYS).toString(),
            "per_page" to "100",
        )
        val announcements = courses.chunked(10).flatMap { batch ->
            val query = range + batch.map { "context_codes[]" to "course_${it.id}" }
            pages(base, accessToken, "/api/v1/announcements", query).flatMap(::objects).mapNotNull { announcement(it, names) }
        }
        val events = courses.chunked(10).flatMap { batch ->
            val query = range + listOf("type" to "event") + batch.map { "context_codes[]" to "course_${it.id}" }
            pages(base, accessToken, "/api/v1/calendar_events", query).flatMap(::objects).mapNotNull { event(it, names) }
        }
        CanvasSyncPayload(courses.size, (assignments + announcements + events).distinctBy { it.key }.take(3000))
    }

    private data class Course(val id: String, val name: String)

    private fun assignment(row: JSONObject, course: Course): CanvasItem? {
        val id = row.text("id") ?: return null
        val title = row.text("name") ?: return null
        return CanvasItem(
            key = "assignment:${course.id}:$id",
            type = CanvasItemType.ASSIGNMENT,
            courseName = course.name,
            title = title,
            body = plain(row.text("description").orEmpty()),
            dueAt = row.instant("due_at"),
            htmlUrl = row.text("html_url").orEmpty(),
            publishedAt = row.instant("created_at"),
            updatedAt = row.instant("updated_at"),
        )
    }

    private fun announcement(row: JSONObject, names: Map<String, String>): CanvasItem? {
        val id = row.text("id") ?: return null
        val title = row.text("title") ?: return null
        val context = row.text("context_code").orEmpty()
        return CanvasItem(
            key = "announcement:$context:$id",
            type = CanvasItemType.ANNOUNCEMENT,
            courseName = names[context] ?: row.text("context_name") ?: "Canvas 公告",
            title = title,
            body = plain(row.text("message").orEmpty()),
            htmlUrl = row.text("html_url").orEmpty(),
            publishedAt = row.instant("posted_at") ?: row.instant("created_at"),
            updatedAt = row.instant("last_reply_at") ?: row.instant("posted_at") ?: row.instant("created_at"),
        )
    }

    private fun event(row: JSONObject, names: Map<String, String>): CanvasItem? {
        val id = row.text("id") ?: return null
        val title = row.text("title") ?: return null
        val context = row.text("context_code").orEmpty()
        return CanvasItem(
            key = "event:$context:$id",
            type = CanvasItemType.EVENT,
            courseName = names[context] ?: row.text("context_name") ?: "Canvas 日历",
            title = title,
            body = plain(row.text("description").orEmpty()),
            startAt = row.instant("start_at"),
            endAt = row.instant("end_at"),
            htmlUrl = row.text("html_url").orEmpty(),
            publishedAt = row.instant("created_at"),
            updatedAt = row.instant("updated_at") ?: row.instant("created_at"),
        )
    }

    private fun pages(base: String, token: String, path: String, query: List<Pair<String, String>>): List<JSONArray> {
        val result = mutableListOf<JSONArray>()
        var next: URI? = URI(base + path + query(query))
        repeat(20) {
            val uri = next ?: return result
            require(sameOrigin(URI(base), uri)) { "Canvas 返回了其他网站的分页链接，已停止同步" }
            val connection = uri.toURL().openConnection() as HttpURLConnection
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 15_000
            connection.readTimeout = 20_000
            connection.requestMethod = "GET"
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("User-Agent", "ChronoFlow-Android/0.4")
            try {
                val code = connection.responseCode
                val body = readLimited(if (code in 200..299) connection.inputStream else connection.errorStream)
                if (code !in 200..299) throw IllegalStateException(errorMessage(code, body))
                result += JSONArray(body)
                next = nextLink(connection.getHeaderField("Link"))?.let(::URI)
            } finally {
                connection.disconnect()
            }
        }
        if (next != null) throw IllegalStateException("Canvas 返回的数据页数过多，请缩小课程范围后重试")
        return result
    }

    private fun readLimited(stream: java.io.InputStream?): String {
        if (stream == null) return ""
        stream.use {
            val bytes = it.readNBytes(2_000_001)
            require(bytes.size <= 2_000_000) { "Canvas 单页响应过大，已停止同步" }
            return String(bytes, StandardCharsets.UTF_8)
        }
    }

    private fun objects(array: JSONArray): List<JSONObject> = (0 until array.length()).mapNotNull { array.optJSONObject(it) }
    private fun JSONObject.text(key: String): String? = if (has(key) && !isNull(key)) get(key).toString().takeIf { it.isNotBlank() } else null
    private fun JSONObject.instant(key: String): Instant? = text(key)?.let { runCatching { Instant.parse(it) }.getOrNull() }
    private fun query(values: List<Pair<String, String>>): String = if (values.isEmpty()) "" else values.joinToString("&", "?") { "${encode(it.first)}=${encode(it.second)}" }
    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.toString())
    private fun sameOrigin(base: URI, other: URI): Boolean = base.scheme.equals(other.scheme, true) &&
        base.host.equals(other.host, true) && effectivePort(base) == effectivePort(other)
    private fun effectivePort(uri: URI): Int = if (uri.port >= 0) uri.port else if (uri.scheme.equals("https", true)) 443 else 80
    private fun nextLink(header: String?): String? = header.orEmpty().split(',').firstNotNullOfOrNull { part ->
        if (!part.contains("rel=\"next\"")) null else Regex("<([^>]+)>").find(part)?.groupValues?.get(1)
    }
    private fun plain(html: String): String = html
        .replace(Regex("(?is)<(script|style)[^>]*>.*?</\\1>"), " ")
        .replace(Regex("(?i)<br\\s*/?>|</p>|</li>"), "\n")
        .replace(Regex("<[^>]+>"), " ")
        .replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", "\"").replace("&#39;", "'")
        .replace(Regex("[ \\t\\x0B\\f\\r]+"), " ").replace(Regex("\\n{3,}"), "\n\n").trim().take(6000)

    private fun errorMessage(code: Int, body: String): String {
        val detail = runCatching {
            val json = JSONObject(body)
            json.optString("message").takeIf { it.isNotBlank() }
                ?: json.optJSONArray("errors")?.optJSONObject(0)?.optString("message")?.takeIf { it.isNotBlank() }
        }.getOrNull()
        return when (code) {
            401 -> "Canvas Access Token 无效或已过期"
            403 -> "Canvas 拒绝访问，请检查 Token 权限"
            404 -> "未找到 Canvas API，请检查学校 Canvas 地址"
            in 300..399 -> "Canvas 地址发生跳转，请填写登录后地址栏中的学校站点根地址"
            else -> "Canvas 同步失败（HTTP $code）${detail?.let { "：${it.take(160)}" }.orEmpty()}"
        }
    }

    companion object {
        fun normalizeBaseUrl(value: String): String {
            val raw = value.trim().trimEnd('/')
            require(raw.length in 9..500) { "请填写学校 Canvas 地址" }
            val uri = runCatching { URI(raw).normalize() }.getOrElse { throw IllegalArgumentException("Canvas 地址格式无效") }
            require(uri.scheme.equals("https", true) && !uri.host.isNullOrBlank()) { "Canvas 地址必须是有效的 https:// 地址" }
            require(uri.userInfo == null && uri.query == null && uri.fragment == null) { "Canvas 地址不能包含账号、查询参数或片段" }
            return URI("https", null, uri.host.lowercase(), uri.port, uri.path.trimEnd('/').ifBlank { null }, null, null).toString().trimEnd('/')
        }

        fun validateToken(value: String) {
            require(value.length in 8..4096 && value.none { it == '\r' || it == '\n' }) { "请填写有效的 Canvas Access Token" }
        }
    }
}
