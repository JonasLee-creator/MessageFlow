package com.chronoflow.local

import android.content.Context
import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import com.chronoflow.local.data.EncryptedStore
import com.chronoflow.local.data.StateCodec
import com.chronoflow.local.domain.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.time.Instant
import java.util.UUID

class LocalStorageTest {
    @Test fun encryptedRestartAndSchemaRoundTrip() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val directory = File(base.cacheDir, "store-test-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getFilesDir(): File = directory }
        try {
            val now = Instant.parse("2026-10-04T00:00:00Z")
            val initial = LocalState(preferences = Preferences(enabled = true, groups = listOf(GroupRule(Source.QQ, "课程群")), zone = "Asia/Shanghai",
                canvasEnabled = true, canvasBaseUrl = "https://canvas.example.edu", canvasAccessToken = "test-token-secret"))
            val input = Incoming(Source.QQ, "课程群", "实验三明天18:00提交，预计2小时", now)
            val pending = LocalEngine.ingest(initial, input, now)
            val n = pending.notices.single()
            val state = LocalEngine.apply(pending, n.id, n.proposal, now)
            assertEquals(state, StateCodec.decode(StateCodec.encode(state)))
            EncryptedStore(context).save(state)
            assertEquals(state, EncryptedStore(context).load())
            val bytes = File(directory, "local-state.enc").readBytes()
            assertFalse(String(bytes, Charsets.UTF_8).contains("实验三"))
            assertFalse(String(bytes, Charsets.UTF_8).contains("test-token-secret"))
            val changed = state.copy(preferences = state.preferences.copy(enabled = false))
            EncryptedStore(context).save(changed)
            assertEquals(changed, EncryptedStore(context).load())
        } finally { directory.deleteRecursively() }
    }
}
