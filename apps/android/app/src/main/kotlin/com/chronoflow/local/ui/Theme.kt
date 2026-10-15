package com.chronoflow.local.ui

import android.app.Activity
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import com.chronoflow.local.R

val Brand = Color(0xFF5B54E6)
val Teal = Brand
val Ink = Color(0xFF1B1830)
val Paper = Color(0xFFF4F2F8)
val Muted = Color(0xFF8B8798)
private val BrandSoft = Color(0xFFEEEDFF)

val NotoSansSc = FontFamily(
    Font(R.font.noto_sans_sc_regular, FontWeight.Normal),
    Font(R.font.noto_sans_sc_medium, FontWeight.Medium),
    Font(R.font.noto_sans_sc_bold, FontWeight.SemiBold),
    Font(R.font.noto_sans_sc_bold, FontWeight.Bold),
)

private fun TextStyle.asNoto(size: Int, line: Int, weight: FontWeight = fontWeight ?: FontWeight.Normal) =
    copy(fontFamily = NotoSansSc, fontWeight = weight, fontSize = size.sp, lineHeight = line.sp)

private val BaseType = Typography()
private val ChronoType = Typography(
    displayLarge = BaseType.displayLarge.asNoto(40, 48, FontWeight.Bold),
    displayMedium = BaseType.displayMedium.asNoto(34, 42, FontWeight.Bold),
    displaySmall = BaseType.displaySmall.asNoto(30, 38, FontWeight.Bold),
    headlineLarge = BaseType.headlineLarge.asNoto(32, 40, FontWeight.Bold),
    headlineMedium = BaseType.headlineMedium.asNoto(30, 38, FontWeight.Bold),
    headlineSmall = BaseType.headlineSmall.asNoto(24, 32, FontWeight.Bold),
    titleLarge = BaseType.titleLarge.asNoto(22, 30, FontWeight.Bold),
    titleMedium = BaseType.titleMedium.asNoto(18, 26, FontWeight.SemiBold),
    titleSmall = BaseType.titleSmall.asNoto(16, 22, FontWeight.Medium),
    bodyLarge = BaseType.bodyLarge.asNoto(17, 26),
    bodyMedium = BaseType.bodyMedium.asNoto(16, 24),
    bodySmall = BaseType.bodySmall.asNoto(14, 22),
    labelLarge = BaseType.labelLarge.asNoto(15, 20, FontWeight.Medium),
    labelMedium = BaseType.labelMedium.asNoto(13, 18, FontWeight.Medium),
    labelSmall = BaseType.labelSmall.asNoto(12, 16, FontWeight.Medium),
)

@Composable fun ChronoTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Brand, onPrimary = Color.White,
            primaryContainer = BrandSoft, onPrimaryContainer = Ink,
            background = Paper, surface = Paper, onSurface = Ink,
            secondary = Color(0xFFA38651),
        ),
        typography = ChronoType,
        content = content,
    )
}

@Composable fun SystemBars(status: Color, navigation: Color, lightStatus: Boolean, lightNavigation: Boolean) {
    val view = LocalView.current
    if (view.isInEditMode) return
    val statusColor = status.toArgb()
    val navigationColor = navigation.toArgb()
    SideEffect {
        val window = (view.context as Activity).window
        window.statusBarColor = statusColor
        window.navigationBarColor = navigationColor
        WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = lightStatus
            isAppearanceLightNavigationBars = lightNavigation
        }
    }
}
