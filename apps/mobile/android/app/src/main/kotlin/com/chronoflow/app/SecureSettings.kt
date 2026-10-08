package com.chronoflow.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Tokens and queued message bodies are encrypted with a non-exportable device key. */
class SecureSettings(context: Context) {
    private val prefs = context.getSharedPreferences("chronoflow_settings", Context.MODE_PRIVATE)
    private fun key(): SecretKey = synchronized(KEY_LOCK) {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("chronoflow-v1", null) as? SecretKey) ?: run {
            val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            generator.init(KeyGenParameterSpec.Builder("chronoflow-v1", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generator.generateKey()
        }
    }
    fun encrypt(text: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        return Base64.encodeToString(cipher.iv + cipher.doFinal(text.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
    }
    fun decrypt(value: String): String {
        val bytes = Base64.decode(value, Base64.NO_WRAP)
        require(bytes.size > 12)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        return String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8)
    }
    val token: String get() = prefs.getString("token", null)?.let { runCatching { decrypt(it) }.getOrDefault("") } ?: ""
    val baseUrl: String get() = prefs.getString("baseUrl", "") ?: ""
    val enabled: Boolean get() = prefs.getBoolean("enabled", false)
    val groups: List<String> get() {
        val array = JSONArray(prefs.getString("groups", "[]"))
        return (0 until array.length()).map { array.getString(it) }
    }
    val uploadError: String get() = prefs.getString("uploadError", "") ?: ""
    fun error(message: String) { prefs.edit().putString("uploadError", message).apply() }
    fun configure(values: Map<*, *>) {
        val edit = prefs.edit()
        if (values.containsKey("baseUrl")) edit.putString("baseUrl", values["baseUrl"] as String)
        if (values.containsKey("token")) {
            val token = values["token"] as String
            if (token.isEmpty()) edit.remove("token") else edit.putString("token", encrypt(token))
        }
        if (values.containsKey("enabled")) edit.putBoolean("enabled", values["enabled"] as Boolean)
        if (values.containsKey("groups")) edit.putString("groups", JSONArray(values["groups"] as List<*>).toString())
        edit.commit()
    }
    companion object { private val KEY_LOCK = Any() }
}
