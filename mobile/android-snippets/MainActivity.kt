import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Text(text = "选择角色入口", style = MaterialTheme.typography.headlineMedium)
                    listOf("elder" to "老人端", "family" to "子女端", "community" to "社区端").forEach { (role, label) ->
                        Button(
                            modifier = Modifier.fillMaxWidth(),
                            onClick = { openMonitor(role) },
                        ) {
                            Text(label)
                        }
                    }
                }
            }
        }
    }

    private fun openMonitor(role: String) {
        startActivity(RealTimeMonitorActivity.intent(this, role))
    }
}
