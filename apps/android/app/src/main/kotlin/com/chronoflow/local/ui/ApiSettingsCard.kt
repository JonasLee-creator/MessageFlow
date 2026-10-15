package com.chronoflow.local.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.chronoflow.local.BuildConfig
import com.chronoflow.local.domain.*

@Composable fun ApiSettingsCard(p: Preferences, busy: Boolean, status: String, onSave: (Preferences) -> Unit, onTest: (Preferences) -> Unit) {
    var enabled by rememberSaveable(p.aiEnabled) { mutableStateOf(p.aiEnabled) }
    var mode by rememberSaveable(p.aiApiMode) { mutableStateOf(if (BuildConfig.ALLOW_OFFICIAL_API) p.aiApiMode else ApiMode.USER) }
    var base by rememberSaveable(p.aiBaseUrl) { mutableStateOf(p.aiBaseUrl) }
    var model by rememberSaveable(p.deepSeekModel) { mutableStateOf(p.deepSeekModel) }
    var gateway by rememberSaveable(p.officialGatewayUrl) { mutableStateOf(p.officialGatewayUrl.ifBlank { BuildConfig.OFFICIAL_GATEWAY_URL }) }
    var key by remember(p.deepSeekApiKey) { mutableStateOf(p.deepSeekApiKey) }
    var code by remember(p.officialAccessCode) { mutableStateOf(p.officialAccessCode) }
    var message by remember { mutableStateOf<String?>(null) }
    fun settings() = p.copy(aiEnabled = enabled, aiApiMode = if (BuildConfig.ALLOW_OFFICIAL_API) mode else ApiMode.USER, aiBaseUrl = base.trim(), deepSeekModel = model.trim(), deepSeekApiKey = key.trim(), officialGatewayUrl = gateway.trim(), officialAccessCode = code.trim())
    fun apply(test: Boolean) {
        val next = settings()
        runCatching { AiApiPolicy.validate(if (test) next.copy(aiEnabled = true) else next, BuildConfig.ALLOW_OFFICIAL_API) }
            .onSuccess { message = null; if (test) onTest(next) else onSave(next) }
            .onFailure { message = it.message }
    }
    Panel {
        Text("AI 接口", style = MaterialTheme.typography.titleMedium)
        Text("选择官方接口或使用自己的模型服务。识别结果核对后才会更新计划。", style = MaterialTheme.typography.bodySmall, color = Muted)
        Toggle("允许使用 AI 分析", enabled, enabled = !busy) { enabled = it }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(mode == ApiMode.OFFICIAL && BuildConfig.ALLOW_OFFICIAL_API, { mode = ApiMode.OFFICIAL }, enabled = !busy && BuildConfig.ALLOW_OFFICIAL_API, label = { Text("官方接口") })
            FilterChip(mode == ApiMode.USER || !BuildConfig.ALLOW_OFFICIAL_API, { mode = ApiMode.USER }, enabled = !busy, label = { Text("用户接口") })
        }
        if (!BuildConfig.ALLOW_OFFICIAL_API) Text("当前版本使用用户接口，请填写自己的模型服务配置。", style = MaterialTheme.typography.bodySmall, color = Muted)
        if (mode == ApiMode.OFFICIAL && BuildConfig.ALLOW_OFFICIAL_API) {
            Text("由时序提供模型服务，开发者密钥保存在服务器。", style = MaterialTheme.typography.bodySmall, color = Muted)
            OutlinedTextField(gateway, { gateway = it }, label = { Text("官方服务地址") }, placeholder = { Text("https://chronoflow.example.com") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
            OutlinedTextField(code, { code = it }, label = { Text("官方接口体验码") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy, visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
        } else {
            OutlinedTextField(base, { base = it }, label = { Text("接口地址（Base URL）") }, placeholder = { Text("https://api.example.com/v1") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
            OutlinedTextField(model, { model = it }, label = { Text("模型名称") }, supportingText = { Text("填写服务商实际支持的模型名称") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy)
            OutlinedTextField(key, { key = it }, label = { Text("API Key") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy, visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { apply(false) }, enabled = !busy) { Text("保存配置") }
            OutlinedButton(onClick = { apply(true) }, enabled = !busy) { Text("测试连接") }
        }
        if (p.deepSeekApiKey.isNotBlank() || p.officialAccessCode.isNotBlank()) TextButton(onClick = {
            key = ""; code = ""; enabled = false; onSave(p.copy(aiEnabled = false, deepSeekApiKey = "", officialAccessCode = ""))
        }, enabled = !busy) { Text("清除密钥与体验码") }
        Text(status, style = MaterialTheme.typography.bodySmall, color = Teal)
        message?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        Text("通知正文、群名及相关事项将发送到所选模型服务。用户接口直接连接服务商；官方接口通过时序服务器转发。密钥和体验码由 Android Keystore 加密保护，退出登录时清除。连接测试可能产生模型费用。", style = MaterialTheme.typography.bodySmall, color = Muted)
    }
}
