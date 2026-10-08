package com.chronoflow.local.ui

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Teal = Color(0xFF16776A)
val Ink = Color(0xFF1B3331)
val Paper = Color(0xFFF4F7F2)
val Muted = Color(0xFF677872)

@Composable fun ChronoTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = lightColorScheme(primary = Teal, onPrimary = Color.White,
        primaryContainer = Color(0xFFDDEEE4), onPrimaryContainer = Ink,
        background = Paper, surface = Paper, onSurface = Ink, secondary = Color(0xFF8C693A)), content = content)
}
