package com.chronoflow.local

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import com.chronoflow.local.data.AccountStore
import com.chronoflow.local.data.EncryptedStore
import com.chronoflow.local.data.StateCodec
import com.chronoflow.local.domain.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.UUID

class AccountStorageTest {
    @Test fun accountsAndGuestWorkspacesRemainSeparate() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val directory = File(base.cacheDir, "account-test-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getFilesDir(): File = directory }
        try {
            val accounts = AccountStore(context)
            assertNull(accounts.activeSession())
            val first = accounts.register("TestUser", "offline-password", "offline-password")
            assertEquals(first, accounts.login("testuser", "offline-password"))
            assertTrue(runCatching { accounts.login("testuser", "wrong-password") }.isFailure)
            assertTrue(runCatching { accounts.register("TESTUSER", "offline-password", "offline-password") }.isFailure)
            val second = accounts.register("用户乙", "other-password", "other-password")
            EncryptedStore(context).save(LocalState(tasks = listOf(Task(title = "游客任务"))))
            EncryptedStore(context, first.userId).save(LocalState(tasks = listOf(Task(title = "账号任务"))))
            assertTrue(EncryptedStore(context, second.userId).load().tasks.isEmpty())
            assertEquals("游客任务", EncryptedStore(context).load().tasks.single().title)
            assertEquals("账号任务", EncryptedStore(context, first.userId).load().tasks.single().title)
            accounts.rememberSession(first)
            assertEquals(first, AccountStore(context).activeSession())
            accounts.rememberSession(null)
            assertNull(AccountStore(context).activeSession())
            assertFalse(File(directory, "accounts-v1.enc").readText().contains("offline-password"))
            val old = JSONObject(String(StateCodec.encode(LocalState()), Charsets.UTF_8)).put("schema", 2)
            old.getJSONObject("preferences").apply { remove("aiApiMode"); remove("aiBaseUrl"); remove("officialGatewayUrl"); remove("officialAccessCode") }
            assertEquals(ApiMode.USER, StateCodec.decode(old.toString().toByteArray()).preferences.aiApiMode)
        } finally { directory.deleteRecursively() }
    }
}
