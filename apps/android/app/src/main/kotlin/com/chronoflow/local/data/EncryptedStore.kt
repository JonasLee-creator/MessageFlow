package com.chronoflow.local.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import com.chronoflow.local.domain.LocalState
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class EncryptedFile(context: Context, filename: String) {
    init { require(filename.matches(Regex("[a-zA-Z0-9_-]+\\.enc"))) }
    private val file = AtomicFile(File(context.filesDir, filename))
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (store.getKey("chronoflow-local-v1", null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder("chronoflow-local-v1", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generateKey()
        }
    }
    fun load(): ByteArray? {
        val bytes = try { file.readFully() } catch (e: java.io.FileNotFoundException) { return null }
        require(bytes.size > 12) { "本地文件不完整" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        return cipher.doFinal(bytes.copyOfRange(12, bytes.size))
    }
    fun save(content: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val bytes = cipher.iv + cipher.doFinal(content)
        val stream = file.startWrite()
        try { stream.write(bytes); file.finishWrite(stream) }
        catch (e: Exception) { file.failWrite(stream); throw e }
    }
}

class EncryptedStore(context: Context, userId: String? = null) {
    init { require(userId == null || userId.matches(Regex("[a-f0-9]{32}"))) }
    private val file = EncryptedFile(context, if (userId == null) "local-state.enc" else "workspace-$userId.enc")
    fun load(): LocalState = file.load()?.let(StateCodec::decode) ?: LocalState()
    fun save(state: LocalState) = file.save(StateCodec.encode(state))
}
