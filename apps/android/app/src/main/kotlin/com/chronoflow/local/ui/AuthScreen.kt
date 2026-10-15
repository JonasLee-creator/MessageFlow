package com.chronoflow.local.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AllInclusive
import androidx.compose.material.icons.outlined.ArrowForward
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable fun ChronoRoot(vm: AppViewModel) {
    val workspace by vm.repository.workspace.collectAsStateWithLifecycle()
    val initialized by vm.repository.initialized.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val diskError by vm.repository.storageError.collectAsStateWithLifecycle()
    if (workspace.session == null) {
        AuthScreen(busy || !initialized || diskError != null, diskError ?: error,
            onLogin = { name, password -> vm.run { vm.repository.login(name, password) } },
            onRegister = { name, password, confirmation -> vm.run { vm.repository.register(name, password, confirmation) } },
            onGuest = { vm.run { vm.repository.enterGuest() } }, onClearError = { vm.error.value = null })
    } else key(workspace.session!!.workspace) { ChronoScreen(vm) }
}

@Composable private fun AuthScreen(
    busy: Boolean, error: String?, onLogin: (String, String) -> Unit,
    onRegister: (String, String, String) -> Unit, onGuest: () -> Unit, onClearError: () -> Unit,
) {
    var registering by rememberSaveable { mutableStateOf(false) }
    var username by rememberSaveable { mutableStateOf("") }
    // Never place passwords in the Activity saved-state bundle.
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    var visible by remember { mutableStateOf(false) }
    SystemBars(status = Color(0xFF2A2648), navigation = Color(0xFF1B1830), lightStatus = false, lightNavigation = false)
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFF2A2648), Color(0xFF1B1830)))).safeDrawingPadding().imePadding()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 26.dp, end = 26.dp, top = 34.dp, bottom = 86.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(42.dp).background(Brand, RoundedCornerShape(13.dp)), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.AllInclusive, null, tint = Color.White) }
                Spacer(Modifier.width(12.dp))
                Column { Text("时序", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Color.White); Text("CHRONOFLOW", style = MaterialTheme.typography.labelSmall, color = Color(0xFFA39DBD), letterSpacing = 2.sp) }
            }
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text("把时间，留给重要的事。", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = Color.White)
                Text("从纷杂的信息，到清晰的下一步。", color = Color(0xFFB7B0C9), style = MaterialTheme.typography.bodyMedium)
            }
            Panel {
                Text(if (registering) "创建你的时序账号" else "欢迎回到时序", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text(if (registering) "为每一天，留一份清晰。" else "登录工作空间，接续今天的计划。", color = Muted, style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(username, { username = it.take(24); onClearError() }, label = { Text("用户名") }, placeholder = { Text(if (registering) "2–24个字" else "请输入用户名") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy)
                OutlinedTextField(password, { password = it.take(128); onClearError() }, label = { Text("密码") }, placeholder = { Text(if (registering) "设置8–128位密码" else "请输入密码") },
                    modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !busy,
                    visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), trailingIcon = {
                        IconButton(onClick = { visible = !visible }, enabled = !busy) { Icon(if (visible) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility, if (visible) "隐藏密码" else "显示密码") }
                    })
                if (registering) OutlinedTextField(confirmation, { confirmation = it.take(128); onClearError() }, label = { Text("确认密码") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                    enabled = !busy, visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                Button(onClick = { if (registering) onRegister(username, password, confirmation) else onLogin(username, password) }, enabled = !busy, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                    Text(if (registering) "注册并进入" else "登录"); Spacer(Modifier.width(8.dp)); Icon(Icons.Outlined.ArrowForward, null)
                }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
                    Text(if (registering) "已经有账号？" else "还没有账号？", style = MaterialTheme.typography.bodySmall, color = Muted)
                    TextButton(onClick = { registering = !registering; password = ""; confirmation = ""; visible = false; onClearError() }, enabled = !busy) { Text(if (registering) "返回登录" else "创建账号") }
                }
                Text("账号与工作空间数据加密保存在当前手机", style = MaterialTheme.typography.labelSmall, color = Muted)
            }
        }
        TextButton(onClick = onGuest, enabled = !busy, modifier = Modifier.align(Alignment.BottomEnd).padding(14.dp)) { Text("游客模式", color = Color(0xFFDDD6EE)); Spacer(Modifier.width(5.dp)); Icon(Icons.Outlined.ArrowForward, null, tint = Color(0xFFDDD6EE)) }
    }
}
