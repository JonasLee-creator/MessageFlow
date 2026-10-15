package com.chronoflow.local.data

import android.content.Context
import com.chronoflow.local.domain.LocalSession
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom
import java.text.Normalizer
import java.util.Locale
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** Device-local accounts; not a cloud identity or a cross-device sign-in service. */
class AccountStore(context: Context) {
    private val file = EncryptedFile(context, "accounts-v1.enc")
    private val random = SecureRandom()
    private val iterations = 310000
    private fun root(): JSONObject = file.load()?.let { JSONObject(String(it, Charsets.UTF_8)).also { value ->
        require(value.getInt("schema") == 1 && value.optJSONArray("accounts") != null) { "账号记录无法读取" }
    } } ?: JSONObject().put("schema", 1).put("accounts", JSONArray())
    private fun save(root: JSONObject) = file.save(root.toString().toByteArray(Charsets.UTF_8))
    private fun normalize(value: String) = Normalizer.normalize(value, Normalizer.Form.NFKC).trim()
    private fun key(value: String) = normalize(value).lowercase(Locale.ROOT)
    private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
    private fun bytes(value: String): ByteArray {
        require(value.length % 2 == 0 && value.all { it in "0123456789abcdef" }) { "账号校验记录无效" }
        return value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }
    private fun derive(password: String, salt: ByteArray): ByteArray {
        val spec = PBEKeySpec(password.toCharArray(), salt, iterations, 256)
        return try { SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded }
        finally { spec.clearPassword() }
    }
    private fun rows(root: JSONObject) = root.getJSONArray("accounts").let { a -> (0 until a.length()).map(a::getJSONObject) }
    fun activeSession(): LocalSession? {
        val root = root(); val saved = root.optJSONObject("session") ?: return null
        if (saved.optBoolean("guest")) return LocalSession()
        val account = rows(root).firstOrNull { it.getString("id") == saved.optString("userId") } ?: return null
        require(account.getString("id").matches(Regex("[a-f0-9]{32}"))) { "账号标识无效" }
        return LocalSession(account.getString("id"), account.getString("username"))
    }
    fun rememberSession(session: LocalSession?) {
        val root = root()
        if (session == null) root.remove("session")
        else root.put("session", JSONObject().put("guest", session.isGuest).put("userId", session.userId ?: JSONObject.NULL))
        save(root)
    }
    fun register(username: String, password: String, confirmation: String): LocalSession {
        val name = normalize(username)
        require(name.matches(Regex("[\\p{L}\\p{N}_-]{2,24}"))) { "用户名需为2–24个字，可使用文字、数字、下划线或短横线" }
        require(password.length in 8..128 && password.isNotBlank()) { "请设置8–128位密码" }
        require(password == confirmation) { "两次输入的密码不一致" }
        val root = root()
        require(rows(root).none { it.getString("usernameKey") == key(name) }) { "用户名已被使用，请更换或直接登录" }
        val salt = ByteArray(16).also(random::nextBytes); val id = hex(ByteArray(16).also(random::nextBytes))
        root.getJSONArray("accounts").put(JSONObject().put("id", id).put("username", name).put("usernameKey", key(name))
            .put("salt", hex(salt)).put("verifier", hex(derive(password, salt))).put("iterations", iterations))
        save(root)
        return LocalSession(id, name)
    }
    fun login(username: String, password: String): LocalSession {
        require(username.isNotBlank() && password.isNotEmpty() && password.length <= 128) { "请输入有效的用户名和密码" }
        val account = rows(root()).firstOrNull { it.getString("usernameKey") == key(username) }
        val salt = account?.getString("salt")?.let(::bytes) ?: ByteArray(16)
        require(salt.size == 16 && (account == null || account.getInt("iterations") == iterations)) { "账号校验记录无效" }
        val expected = account?.getString("verifier")?.let(::bytes) ?: ByteArray(32)
        val matches = MessageDigest.isEqual(derive(password, salt), expected)
        require(account != null && matches) { "用户名或密码不正确" }
        return LocalSession(account.getString("id"), account.getString("username"))
    }
}
