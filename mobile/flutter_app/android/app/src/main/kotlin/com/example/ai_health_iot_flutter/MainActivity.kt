package com.example.ai_health_iot_flutter

import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.SystemClock
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import kotlin.math.max

class MainActivity : FlutterActivity() {
    companion object {
        private const val PCM_STREAM_CHANNEL = "ai_health_iot/pcm_stream"
    }

    private val audioExecutor = ThreadPoolExecutor(
        1,
        1,
        0L,
        TimeUnit.MILLISECONDS,
        LinkedBlockingQueue(),
    )

    @Volatile
    private var audioTrack: AudioTrack? = null

    @Volatile
    private var streamGeneration = 0

    private var totalBytesWritten = 0L
    private var currentFrameBytes = 2
    private var currentSampleRate = 24000

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            PCM_STREAM_CHANNEL,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> {
                    val sampleRate = call.argument<Int>("sampleRate") ?: 24000
                    val channels = call.argument<Int>("channels") ?: 1
                    if (sampleRate <= 0 || channels !in 1..2) {
                        result.success(false)
                        return@setMethodCallHandler
                    }

                    val generation = ++streamGeneration
                    audioExecutor.execute {
                        val started = generation == streamGeneration &&
                            startAudioTrack(sampleRate, channels)
                        runOnUiThread { result.success(started) }
                    }
                }

                "write" -> {
                    val data = call.argument<ByteArray>("data")
                    val track = audioTrack
                    if (data == null || data.isEmpty() || track == null) {
                        result.success(false)
                        return@setMethodCallHandler
                    }

                    val generation = streamGeneration
                    audioExecutor.execute {
                        if (generation == streamGeneration) {
                            writePcmBytes(data)
                        }
                    }
                    result.success(true)
                }

                "finish" -> {
                    val generation = streamGeneration
                    audioExecutor.execute {
                        val finished = generation == streamGeneration &&
                            finishAudioTrack()
                        runOnUiThread { result.success(finished) }
                    }
                }

                "abort" -> {
                    ++streamGeneration
                    audioExecutor.queue.clear()
                    audioExecutor.execute {
                        releaseAudioTrack(flush = true)
                        runOnUiThread { result.success(null) }
                    }
                }

                else -> result.notImplemented()
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun startAudioTrack(sampleRate: Int, channels: Int): Boolean {
        releaseAudioTrack(flush = true)
        val channelConfig = if (channels == 1) {
            AudioFormat.CHANNEL_OUT_MONO
        } else {
            AudioFormat.CHANNEL_OUT_STEREO
        }
        val minBufferBytes = AudioTrack.getMinBufferSize(
            sampleRate,
            channelConfig,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        val targetBufferBytes = sampleRate * channels * 2 / 2
        val bufferBytes = max(
            if (minBufferBytes > 0) minBufferBytes else 0,
            targetBufferBytes,
        )

        val track = AudioTrack(
            AudioManager.STREAM_MUSIC,
            sampleRate,
            channelConfig,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferBytes,
            AudioTrack.MODE_STREAM,
        )
        if (track.state != AudioTrack.STATE_INITIALIZED) {
            track.release()
            return false
        }

        currentSampleRate = sampleRate
        currentFrameBytes = channels * 2
        totalBytesWritten = 0L
        audioTrack = track
        track.play()
        return true
    }

    @Suppress("DEPRECATION")
    private fun writePcmBytes(data: ByteArray) {
        val track = audioTrack ?: return
        var offset = 0
        while (offset < data.size && track.state == AudioTrack.STATE_INITIALIZED) {
            val written = track.write(data, offset, data.size - offset)
            if (written <= 0) {
                break
            }
            offset += written
        }
        totalBytesWritten += offset
    }

    private fun finishAudioTrack(): Boolean {
        val track = audioTrack ?: return false
        val expectedFrames = totalBytesWritten / currentFrameBytes
        val expectedDurationMs =
            (expectedFrames * 1000L / currentSampleRate).coerceAtLeast(0L)
        val deadline = SystemClock.elapsedRealtime() + expectedDurationMs + 2000L

        var playedFrames = track.playbackHeadPosition.toLong() and 0xffffffffL
        while (
            playedFrames < expectedFrames &&
            SystemClock.elapsedRealtime() < deadline &&
            track.state == AudioTrack.STATE_INITIALIZED
        ) {
            Thread.sleep(20L)
            playedFrames = track.playbackHeadPosition.toLong() and 0xffffffffL
        }

        val drained = playedFrames >= expectedFrames
        releaseAudioTrack(flush = false)
        return drained
    }

    private fun releaseAudioTrack(flush: Boolean) {
        val track = audioTrack ?: return
        audioTrack = null
        try {
            if (flush) {
                track.pause()
                track.flush()
            } else {
                track.stop()
            }
        } catch (_: IllegalStateException) {
            // The track may already be stopped after an output-route change.
        } finally {
            track.release()
            totalBytesWritten = 0L
        }
    }

    override fun onDestroy() {
        ++streamGeneration
        audioExecutor.queue.clear()
        audioExecutor.execute { releaseAudioTrack(flush = true) }
        audioExecutor.shutdown()
        super.onDestroy()
    }
}
