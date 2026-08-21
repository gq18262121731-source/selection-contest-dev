import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class RealTimeMonitorActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val role = intent.getStringExtra(EXTRA_ROLE).orEmpty()
        setContent {
            MaterialTheme {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(text = "实时监测 - $role", style = MaterialTheme.typography.headlineMedium)
                    listOf("心率 82 bpm", "体温 36.6℃", "血氧 97%", "血压 118/76").forEach { item ->
                        Card(modifier = Modifier.fillMaxWidth()) {
                            Text(text = item, modifier = Modifier.padding(18.dp))
                        }
                    }
                    Text(
                        text = "这里可继续接入 WebSocket、告警弹窗和 AI 建议流式输出。",
                        style = MaterialTheme.typography.bodyLarge,
                    )
                }
            }
        }
    }

    companion object {
        private const val EXTRA_ROLE = "role"

        fun intent(context: Context, role: String): Intent {
            return Intent(context, RealTimeMonitorActivity::class.java).putExtra(EXTRA_ROLE, role)
        }
    }
}
