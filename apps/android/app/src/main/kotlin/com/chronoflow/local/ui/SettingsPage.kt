package com.chronoflow.local.ui

import android.Manifest
import android.content.ComponentName
import android.content.Intent
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
import com.chronoflow.local.accessibility.WeChatAccessibilityService
import com.chronoflow.local.domain.*
import com.chronoflow.local.notifications.GroupNotificationListener
import com.chronoflow.local.notifications.Reminders

private fun access(context: android.content.Context): Boolean {
    val raw = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners").orEmpty()
    val component = ComponentName(context, GroupNotificationListener::class.java)
    return raw.split(':').any { ComponentName.unflattenFromString(it) == component }
}

private fun accessibilityAccess(context: android.content.Context): Boolean {
    if (Settings.Secure.getInt(context.contentResolver, Settings.Secure.ACCESSIBILITY_ENABLED, 0) != 1) return false
    val raw = Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
    val component = ComponentName(context, WeChatAccessibilityService::class.java)
    return raw.split(':').any { ComponentName.unflattenFromString(it) == component }
}

@Composable fun SettingsPage(
    p: Preferences,
    busy: Boolean,
    lastNotification: String,
    lastAccessibilityCapture: String,
    onSave: (Preferences) -> Unit,
) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    var granted by remember { mutableStateOf(access(context)) }
    var accessibilityGranted by remember { mutableStateOf(accessibilityAccess(context)) }
    var remindersGranted by remember { mutableStateOf(Reminders.allowed(context)) }
    var source by rememberSaveable { mutableStateOf(Source.WECHAT.name) }
    var group by rememberSaveable { mutableStateOf("") }
    var start by rememberSaveable(p.startHour) { mutableStateOf(p.startHour.toString()) }
    var end by rememberSaveable(p.endHour) { mutableStateOf(p.endHour.toString()) }
    var aiEnabled by rememberSaveable(p.aiEnabled) { mutableStateOf(p.aiEnabled) }
    var apiKey by rememberSaveable(p.deepSeekApiKey) { mutableStateOf(p.deepSeekApiKey) }
    var aiModel by rememberSaveable(p.deepSeekModel) { mutableStateOf(p.deepSeekModel) }
    var message by remember { mutableStateOf<String?>(null) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { remindersGranted = Reminders.allowed(context) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) {
            granted = access(context)
            accessibilityGranted = accessibilityAccess(context)
            remindersGranted = Reminders.allowed(context)
        } }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { PageHeading("YOUR PHONE. YOUR DATA.", "连接，你的信息。", "计划加密保存在手机；是否启用 DeepSeek 由你决定。") }
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
                TextButton(onClick = {
                    val groups = p.groups - rule
                    onSave(p.copy(
                        groups = groups,
                        enabled = p.enabled && groups.isNotEmpty(),
                        accessibilityCaptureEnabled = p.accessibilityCaptureEnabled && groups.any { it.source == Source.WECHAT },
                    ))
                }, enabled = !busy) { Text("移除") }
            } }
        } }
        item { Panel {
            Text("DeepSeek AI 助手", style = MaterialTheme.typography.titleMedium)
            Text("启用后，白名单通知正文、群名和相关事项会发送到 DeepSeek，用于多事项拆分、上下文追踪、追问、任务拆解与可信度分析。", style = MaterialTheme.typography.bodySmall)
            Toggle("允许使用 DeepSeek 分析", aiEnabled, enabled = !busy) { aiEnabled = it }
            OutlinedTextField(apiKey, { apiKey = it.trim() }, label = { Text("DeepSeek API Key") },
                placeholder = { Text("sk-…") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            OutlinedTextField(aiModel, { aiModel = it.trim() }, label = { Text("模型") },
                supportingText = { Text("默认 deepseek-flash；也可填写账户支持的其他模型") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    if (aiEnabled && apiKey.length !in 8..512) message = "请填写有效的 DeepSeek API Key"
                    else if (aiModel.isBlank() || aiModel.any { it.isWhitespace() }) message = "模型名称无效"
                    else { onSave(p.copy(aiEnabled = aiEnabled, deepSeekApiKey = apiKey, deepSeekModel = aiModel)); message = null }
                }, enabled = !busy) { Text("保存 AI 设置") }
                if (p.deepSeekApiKey.isNotBlank()) TextButton(onClick = {
                    apiKey = ""; aiEnabled = false; onSave(p.copy(aiEnabled = false, deepSeekApiKey = "")); message = null
                }, enabled = !busy) { Text("清除密钥") }
            }
            Text("API Key 随其他数据使用 Android Keystore 加密保存在本机；请求会产生 DeepSeek API 费用。AI 结果始终先进入「发现」供你核对。", style = MaterialTheme.typography.bodySmall, color = Muted)
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
            Toggle("自动应用明确的新建事项", p.autoCreate, enabled = !busy) { onSave(p.copy(autoCreate = it)) }
            Text("默认先确认。开启自动应用后，仅自动接受日期、时间和耗时完整且无歧义的新事项；修改、取消及模糊信息仍需确认。", style = MaterialTheme.typography.bodySmall, color = Muted)
        } }
        item { Panel {
            Text("3 · 微信前台采集（可选）", style = MaterialTheme.typography.titleMedium)
            Text(
                "解决你正在使用微信时系统不弹通知的问题。需要你在系统设置授权，并在本页单独开启；两项同时满足才会采集。",
                style = MaterialTheme.typography.bodySmall,
            )
            Text(if (accessibilityGranted) "系统无障碍授权已开启" else "系统无障碍授权未开启", color = Teal)
            Text(
                "授权后，Android 允许此服务查看微信前台页面。时序只注册微信，只在页面顶部精确匹配白名单群后处理消息区；不会点击、滑动、输入，也不访问微信后台聊天数据库。",
                style = MaterialTheme.typography.bodySmall,
                color = Muted,
            )
            OutlinedButton(onClick = {
                runCatching { context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
                    .onFailure { message = "无法打开设置，请在系统设置中搜索“无障碍”或“已下载的应用”。" }
            }) { Text("打开无障碍授权设置") }
            Toggle("允许微信前台白名单采集", p.accessibilityCaptureEnabled, enabled = !busy) { enabled ->
                val hasWeChatGroup = p.groups.any { it.source == Source.WECHAT }
                when {
                    enabled && !hasWeChatGroup -> message = "请先添加至少一个微信白名单群"
                    enabled && !accessibilityGranted -> message = "请先在系统无障碍设置中开启“时序 · 微信前台白名单采集”"
                    else -> {
                        onSave(p.copy(accessibilityCaptureEnabled = enabled))
                        message = null
                    }
                }
            }
            Text("采集诊断：$lastAccessibilityCapture", style = MaterialTheme.typography.bodySmall, color = Muted)
            Text(
                "首次进入白名单群只建立当前屏幕基线；之后新出现的文字才会进入识别。手动向上滚动显示的历史消息会被忽略。启用 DeepSeek 时，捕捉到的新文字会按上方 AI 授权说明发送给 DeepSeek。",
                style = MaterialTheme.typography.bodySmall,
                color = Muted,
            )
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
        item { Text("时序 0.4.0\n通知访问可在后台接收系统已展示的通知；可选无障碍功能只补充采集正在前台显示的微信白名单群新文字。\n原始通知最多保留1000条，卸载或清除应用数据会删除本地计划。", style = MaterialTheme.typography.bodySmall, color = Muted, modifier = Modifier.padding(bottom = 20.dp)) }
    }
}
