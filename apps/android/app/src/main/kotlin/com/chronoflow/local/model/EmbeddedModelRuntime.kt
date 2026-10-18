package com.chronoflow.local.model

import android.content.Context
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.FloatBuffer
import java.nio.LongBuffer
import java.security.MessageDigest

/** One interpreter and CPU session per process; serialized work stays off the UI thread. */
object EmbeddedModelRuntime {
    private var session: OrtSession? = null
    private var folder: File? = null
    private val env by lazy { OrtEnvironment.getEnvironment() }
    private val shapes = linkedMapOf(
        "hashed_text" to longArrayOf(1, 2048), "category_id" to longArrayOf(1),
        "course_id" to longArrayOf(1), "numeric_features" to longArrayOf(1, 16),
        "user_state" to longArrayOf(1, 12), "slot_features" to longArrayOf(1, 4, 12),
        "slot_user_state" to longArrayOf(1, 4, 12),
    )

    @Synchronized fun plan(context: Context, payload: String): String {
        if (session == null) initialize(context.applicationContext)
        if (!Python.isStarted()) Python.start(AndroidPlatform(context.applicationContext))
        return Python.getInstance().getModule("deployment.android")
            .callAttr("run", payload, this, requireNotNull(folder).absolutePath).toString()
    }

    private fun initialize(context: Context) {
        val target = File(context.noBackupFilesDir, "embedded-model").apply { mkdirs() }
        val manifest = JSONObject(context.assets.open("chronoflow/checksums.json").bufferedReader().use { it.readText() })
        val expectedNames = setOf("chronoflow_predictor.onnx", "feature_config.json", "model_metadata.json")
        require(manifest.keys().asSequence().toSet() == expectedNames) { "内置模型清单无效" }
        for (name in expectedNames) {
            val bytes = context.assets.open("chronoflow/$name").use { it.readBytes() }
            val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 255) }
            require(hash == manifest.getString(name)) { "内置模型校验失败，请重新安装应用" }
            val file = File(target, name)
            // App-private files are refreshed from the verified APK on each process start.
            file.writeBytes(bytes)
        }
        val created = OrtSession.SessionOptions().use { options ->
            options.setIntraOpNumThreads(2)
            options.setInterOpNumThreads(1)
            env.createSession(File(target, "chronoflow_predictor.onnx").absolutePath, options)
        }
        try {
            require(created.inputNames == shapes.keys && created.outputNames.containsAll(listOf("duration_parameters", "execution_logits"))) { "内置模型接口不匹配" }
        } catch (e: Exception) { created.close(); throw e }
        folder = target; session = created
    }

    /** Called only by the embedded Python predictor. All inputs are the shared frozen features. */
    @Synchronized fun infer(inputsJson: String): String {
        val input = JSONObject(inputsJson)
        require(input.keys().asSequence().toSet() == shapes.keys) { "模型特征字段不匹配" }
        val tensors = linkedMapOf<String, OnnxTensor>()
        fun flatten(value: Any, output: MutableList<Double>) {
            if (value is JSONArray) for (i in 0 until value.length()) flatten(value.get(i), output)
            else { require(value is Number && value.toDouble().isFinite()); output += value.toDouble() }
        }
        try {
            for ((name, shape) in shapes) {
                val values = mutableListOf<Double>(); flatten(input.getJSONArray(name), values)
                require(values.size.toLong() == shape.fold(1L) { a, b -> a * b }) { "模型特征维数不匹配" }
                tensors[name] = if (name == "category_id" || name == "course_id") {
                    require(values.all { it == it.toLong().toDouble() })
                    OnnxTensor.createTensor(env, LongBuffer.wrap(values.map { it.toLong() }.toLongArray()), shape)
                } else OnnxTensor.createTensor(env, FloatBuffer.wrap(values.map { it.toFloat() }.toFloatArray()), shape)
            }
            requireNotNull(session).run(tensors).use { result ->
                fun floats(name: String, count: Int): JSONArray {
                    val tensor = result.get(name).orElseThrow { IllegalStateException("缺少模型输出") } as OnnxTensor
                    require(tensor.info.shape.contentEquals(longArrayOf(1, count.toLong()))) { "模型输出维数错误" }
                    val buffer = tensor.floatBuffer
                    return JSONArray().apply { repeat(count) { val v = buffer.get(); require(v.isFinite()); put(v.toDouble()) } }
                }
                return JSONObject().put("duration_parameters", floats("duration_parameters", 2))
                    .put("execution_logits", floats("execution_logits", 4)).toString()
            }
        } finally { tensors.values.forEach { it.close() } }
    }
}
