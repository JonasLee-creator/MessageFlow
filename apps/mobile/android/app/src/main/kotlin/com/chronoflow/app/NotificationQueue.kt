package com.chronoflow.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class NotificationQueue(context: Context) : SQLiteOpenHelper(context, "notifications.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE queue (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at INTEGER NOT NULL)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit
    fun add(id: String, encryptedPayload: String) {
        writableDatabase.insertWithOnConflict("queue", null, ContentValues().apply {
            put("id", id); put("payload", encryptedPayload); put("created_at", System.currentTimeMillis())
        }, SQLiteDatabase.CONFLICT_IGNORE)
        // Retain up to 500 notifications and at most seven days of local content.
        writableDatabase.delete("queue", "created_at < ?", arrayOf((System.currentTimeMillis() - 7L * 86400000).toString()))
        writableDatabase.execSQL("DELETE FROM queue WHERE id NOT IN (SELECT id FROM queue ORDER BY created_at DESC LIMIT 500)")
    }
    fun batch(): List<Pair<String, String>> {
        writableDatabase.delete("queue", "created_at < ?", arrayOf((System.currentTimeMillis() - 7L * 86400000).toString()))
        return readableDatabase.rawQuery("SELECT id, payload FROM queue ORDER BY created_at LIMIT 25", null).use { cursor ->
            buildList { while (cursor.moveToNext()) add(cursor.getString(0) to cursor.getString(1)) }
        }
    }
    fun count(): Int = readableDatabase.rawQuery("SELECT COUNT(*) FROM queue", null).use { it.moveToFirst(); it.getInt(0) }
    fun remove(id: String) { writableDatabase.delete("queue", "id = ?", arrayOf(id)) }
    fun clear() { writableDatabase.delete("queue", null, null) }
}
