package com.chronoflow.local.ui

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.chronoflow.local.domain.*
import com.chronoflow.local.notifications.GroupNotificationListener
import com.chronoflow.local.notifications.Reminders

private fun access(context: android.content.Context): Boolean {
    val raw = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners").orEmpty()
    val component = ComponentName(context, GroupNotificationListener::class.java)
    return raw.split(':').any { ComponentName.unflattenFromString(it) == component }
}

@Composable fun SettingsPage(
    p: Preferences,
    busy: Boolean,
    lastNotification: String,
    canvasStatus: String,
    apiStatus: String,
    onSave: (Preferences) -> Unit,
    onConnectCanvas: (String, String) -> Unit,
    onSyncCanvas: () -> Unit,
    onDisconnectCanvas: () -> Unit,
    onTestApi: (Preferences) -> Unit,
) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    var granted by remember { mutableStateOf(access(context)) }
    var remindersGranted by remember { mutableStateOf(Reminders.allowed(context)) }
    var source by rememberSaveable { mutableStateOf(Source.WECHAT.name) }
    var group by rememberSaveable { mutableStateOf("") }
    var start by rememberSaveable(p.startHour) { mutableStateOf(p.startHour.toString()) }
    var end by rememberSaveable(p.endHour) { mutableStateOf(p.endHour.toString()) }
    var canvasUrl by rememberSaveable(p.canvasBaseUrl) { mutableStateOf(p.canvasBaseUrl) }
    var canvasToken by remember(p.canvasAccessToken) { mutableStateOf(p.canvasAccessToken) }
    var message by remember { mutableStateOf<String?>(null) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { remindersGranted = Reminders.allowed(context) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) {
            granted = access(context)
            remindersGranted = Reminders.allowed(context)
        } }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { PageHeading("YOUR PHONE. YOUR DATA.", "连接，你的信息。", "计划加密保存在手机，信息来源和 AI 接口由你选择。") }
        item { Panel {
            Text("1 · 选择课程群", style = MaterialTheme.typography.titleMedium)
            Text("按微信、QQ 分别填写群名。需与系统通知显示的群名一致，只处理白名单中的通知。", style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(Source.WECHAT, Source.QQ).forEach { item -> FilterChip(source == item.name, { source = item.name }, label = { Text(item.label) }) }
            }
            OutlinedTextField(group, { group = it }, label = { Text("群名，如：计算机网络课程群") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            Button(onClick = {
                if (group.isBlank() || group.trim().length > 100) message = "请填写1–100字的群名"
                else { onSave(p.copy(groups = p.groups + GroupRule(Source.valueOf(source), group.trim()))); group = ""; message = null }
            }, enabled = !busy) { Text("添加到白名单") }
            p.groups.forEach { rule -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${rule.source.label} · ${rule.name}", Modifier.weight(1f).padding(vertical = 12.dp))
                TextButton(onClick = { val groups = p.groups - rule; onSave(p.copy(groups = groups, enabled = p.enabled && groups.isNotEmpty())) }, enabled = !busy) { Text("移除") }
            } }
        } }
        item { ApiSettingsCard(p, busy, apiStatus, onSave, onTestApi) }
        item { Panel {
            Text("Canvas 课程平台", style = MaterialTheme.typography.titleMedium)
            Text("同步已选账号可访问的课程、作业、公告和课程日历。所有新增或变更先进入「发现」，由你确认后才写入日程。", style = MaterialTheme.typography.bodySmall)
            Text("1. 在浏览器登录学校 Canvas。\n2. 进入 Account → Settings → Approved Integrations，创建 Access Token。\n3. 回到此处粘贴学校站点地址和 Token。", style = MaterialTheme.typography.bodySmall, color = Muted)
            OutlinedTextField(canvasUrl, { canvasUrl = it.trim() }, label = { Text("学校 Canvas 地址") },
                placeholder = { Text("https://canvas.example.edu") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
            OutlinedTextField(canvasToken, { canvasToken = it.trim() }, label = { Text("Canvas Access Token") },
                modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    val target = canvasUrl.trim().trimEnd('/').let { if (it.startsWith("https://")) "$it/profile/settings" else it }
                    if (!target.startsWith("https://")) message = "请先填写 https:// 开头的 Canvas 地址"
                    else runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(target))) }
                        .onFailure { message = "无法打开浏览器，请检查 Canvas 地址" }
                }) { Text("打开 Canvas 设置") }
                Button(onClick = {
                    if (!canvasUrl.startsWith("https://") || canvasToken.length !in 8..4096) message = "请填写有效的 Canvas 地址和 Access Token"
                    else { onConnectCanvas(canvasUrl, canvasToken); message = null }
                }, enabled = !busy) { Text(if (p.canvasEnabled) "保存并重新连接" else "连接并同步") }
            }
            if (p.canvasEnabled) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onSyncCanvas, enabled = !busy) { Text("立即同步") }
                TextButton(onClick = {
                    canvasUrl = ""; canvasToken = ""; onDisconnectCanvas(); message = null
                }, enabled = !busy) { Text("断开并清除 Token") }
            }
            Text(canvasStatus, style = MaterialTheme.typography.bodySmall, color = if (canvasStatus.startsWith("同步失败")) MaterialTheme.colorScheme.error else Teal)
            Text("App 不接触 Canvas 密码。Token 与本地计划一起由 Android Keystore 加密，且只发送到你填写的同一 HTTPS Canvas 主机。若学校禁用了个人 Token，需要管理员提供 Canvas Developer Key 后才能改用 OAuth。", style = MaterialTheme.typography.bodySmall, color = Muted)
        } }
        item { Panel {
            Text("2 · 授权通知访问", style = MaterialTheme.typography.titleMedium)
            Text(if (granted) "系统通知访问已授权" else "系统通知访问未授权", color = Teal)
            Text("系统授权可以访问通知。本应用仅处理微信、QQ 白名单群的相关消息，不读取聊天记录。", style = MaterialTheme.typography.bodySmall)
            OutlinedButton(onClick = { runCatching { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }.onFailure { message = "无法打开设置，请在系统设置中查找通知使用权。" } }) { Text("打开系统授权设置") }
            Text("监听诊断：$lastNotification", style = MaterialTheme.typography.bodySmall, color = Muted)
            Toggle("开始采集群通知", p.enabled, enabled = !busy) { enabled ->
                if (enabled && (!granted || p.groups.isEmpty())) message = "请先添加群名并授予通知访问"
                else { onSave(p.copy(enabled = enabled)); message = null }
            }
            Toggle("自动应用明确的规则识别事项", p.autoCreate, enabled = !busy) { onSave(p.copy(autoCreate = it)) }
            Text("默认先确认。开启自动应用后，仅自动接受日期、时间和耗时完整的规则提取新事项；AI 结果、修改、取消及模糊信息始终需要确认。", style = MaterialTheme.typography.bodySmall, color = Muted)
        } }
        item { Panel {
            Text("每天可安排的时间", style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(start, { start = it }, label = { Text("开始小时") }, modifier = Modifier.weight(1f), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                OutlinedTextField(end, { end = it }, label = { Text("结束小时") }, modifier = Modifier.weight(1f), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            }
            OutlinedButton(onClick = {
                val a = start.toIntOrNull(); val b = end.toIntOrNull()
                if (a == null || b == null || a !in 0..23 || b !in 1..24 || a >= b) message = "开始需为0–23，结束需为1–24，且结束晚于开始"
                else { onSave(p.copy(startHour = a, endHour = b)); message = null }
            }, enabled = !busy) { Text("保存并重新排程") }
            Text("排程时区：${p.zone}", style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { onSave(p.copy(zone = java.time.ZoneId.systemDefault().id)) }, enabled = !busy) { Text("使用当前手机时区") }
        } }
        item { Panel {
            Text("日程提醒", style = MaterialTheme.typography.titleMedium)
            Toggle("开启本地开始提醒", p.reminders, enabled = !busy) { onSave(p.copy(reminders = it)) }
            Text(if (remindersGranted) "系统允许显示提醒" else "系统通知未允许，当前无法显示提醒", style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = {
                if (Build.VERSION.SDK_INT >= 33 && !remindersGranted) permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                else runCatching { context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)) }
            }) { Text("设置提醒权限") }
            Text("使用系统普通定时提醒，省电模式或厂商后台限制可能造成延迟，不作为精确闹钟。", style = MaterialTheme.typography.bodySmall, color = Muted)
        } }
        message?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
        item { Text("时序 0.4.0\n微信/QQ仅能提取系统实际展示的通知文字；Canvas 通过官方 API 同步。\n原始通知最多保留1000条，卸载或清除应用数据会删除本地计划与密钥。", style = MaterialTheme.typography.bodySmall, color = Muted, modifier = Modifier.padding(bottom = 20.dp)) }
    }
}
