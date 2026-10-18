import com.intellij.openapi.util.Disposer
import com.intellij.psi.PsiErrorElement
import com.intellij.psi.util.PsiTreeUtil
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment
import org.jetbrains.kotlin.config.CompilerConfiguration
import org.jetbrains.kotlin.psi.KtPsiFactory
import java.io.File

/** Parses Kotlin source with an already installed compiler, without resolving Android dependencies. */
fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    try {
        val environment = KotlinCoreEnvironment.createForProduction(disposable, CompilerConfiguration(), EnvironmentConfigFiles.JVM_CONFIG_FILES)
        val factory = KtPsiFactory(environment.project, false)
        val files = File(args.single()).walkTopDown().filter { it.isFile && (it.extension == "kt" || it.extension == "kts") }.toList()
        var errors = 0
        files.forEach { file ->
            // PSI expects normalized newlines, unlike the command-line compiler.
            val parsed = factory.createFile(file.name, file.readText().replace("\r\n", "\n"))
            PsiTreeUtil.collectElementsOfType(parsed, PsiErrorElement::class.java).forEach { error ->
                errors++
                println("${file.path}:${error.textOffset}: ${error.errorDescription}")
            }
        }
        check(errors == 0) { "$errors Kotlin syntax errors" }
        println("Kotlin PSI syntax: ${files.size} files passed (not Android type-checking)")
    } finally { Disposer.dispose(disposable) }
}
