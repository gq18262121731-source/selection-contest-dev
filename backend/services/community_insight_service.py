from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from urllib import error, parse, request

from agent.analysis_service import HealthDataAnalysisService
from agent.rag_service import RAGService
from backend.config import Settings
from backend.models.alarm_model import AlarmRecord
from backend.models.analytics_model import (
    AgentSourceItem,
    ChartPayload,
    CommunityAgentMeta,
    CommunityAgentSummaryRequest,
    CommunityAgentSummaryResponse,
    CommunityWindowAnalysis,
    CommunityWindowReportResponse,
    DeviceHistoryResponse,
    HighRiskEntity,
    HistoryBucket,
    SensorHistoryPoint,
    WindowKind,
)
from backend.models.device_model import DeviceRecord, DeviceStatus
from backend.models.health_model import HealthSample
from backend.services.alarm_service import AlarmService
from backend.services.care_service import CareService
from backend.services.device_service import DeviceService
from backend.services.health_data_repository import HealthDataRepository
from backend.services.stream_service import StreamService


RISK_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


class CommunityInsightService:
    """Builds deterministic history, analytics, chart, and summary payloads."""

    def __init__(
        self,
        *,
        settings: Settings,
        analysis_service: HealthDataAnalysisService,
        stream_service: StreamService,
        alarm_service: AlarmService,
        device_service: DeviceService,
        care_service: CareService,
        rag_service: RAGService,
        repository: HealthDataRepository,
    ) -> None:
        self._settings = settings
        self._analysis = analysis_service
        self._stream = stream_service
        self._alarm_service = alarm_service
        self._device_service = device_service
        self._care_service = care_service
        self._rag = rag_service
        self._repository = repository

    def get_device_history(
        self,
        *,
        device_mac: str,
        window: WindowKind,
        bucket: HistoryBucket,
    ) -> DeviceHistoryResponse:
        normalized_mac = device_mac.strip().upper()
        start_at, end_at = self._window_range(window)
        if bucket == HistoryBucket.RAW:
            samples = self._repository.list_samples(
                device_mac=normalized_mac,
                start_at=start_at,
                end_at=end_at,
                limit=self._sample_limit(window),
            )
            if not samples:
                samples = self._stream.recent_in_window(
                    normalized_mac,
                    minutes=self._window_minutes(window),
                    limit=self._sample_limit(window),
                )
            points = self._build_history_points(samples, bucket=bucket)
        else:
            points = self._repository.list_rollup_points(
                device_mac=normalized_mac,
                start_at=start_at,
                end_at=end_at,
                bucket=bucket,
            )
            if not points:
                samples = self._stream.recent_in_window(
                    normalized_mac,
                    minutes=self._window_minutes(window),
                    limit=self._sample_limit(window),
                )
                points = self._build_history_points(samples, bucket=bucket)
        return DeviceHistoryResponse(
            device_mac=normalized_mac,
            window=window,
            bucket=bucket,
            points=points,
        )

    def build_window_report(
        self,
        *,
        window: WindowKind,
        device_macs: list[str] | None = None,
    ) -> CommunityWindowReportResponse:
        normalized_macs = self._normalize_macs(device_macs)
        start_at, end_at = self._window_range(window)
        histories = self._repository.list_samples_by_devices(
            device_macs=normalized_macs or None,
            start_at=start_at,
            end_at=end_at,
            per_device_limit=self._sample_limit(window),
        )
        if not histories:
            histories = self._stream.recent_by_devices(
                normalized_macs or None,
                minutes=self._window_minutes(window),
                per_device_limit=self._sample_limit(window),
            )
        devices = self._selected_devices(normalized_macs)
        alarms = self._window_alarms(window=window, device_macs=normalized_macs)
        analysis = self._build_window_analysis(
            window=window,
            histories=histories,
            devices=devices,
            alarms=alarms,
        )
        return CommunityWindowReportResponse(
            window=window,
            generated_at=datetime.now(timezone.utc),
            analysis=analysis,
        )

    def build_agent_summary(
        self,
        payload: CommunityAgentSummaryRequest,
    ) -> CommunityAgentSummaryResponse:
        report = self.build_window_report(window=payload.window, device_macs=payload.device_macs)
        sources, degraded_notes = self._knowledge_sources(
            question=payload.question,
            analysis=report.analysis,
            include_web_search=payload.include_web_search,
        )
        advice = self._build_summary_advice(report.analysis)
        summary_text = self._build_summary_text(
            question=payload.question,
            window=payload.window,
            analysis=report.analysis,
            advice=advice,
        )
        charts = report.analysis.chart_payloads if payload.include_charts else []
        if payload.include_web_search and not self._settings.tavily_api_key:
            degraded_notes.append("tavily_not_configured")
        if not self._settings.qwen_model or not self._settings.qwen_api_key or not self._settings.qwen_api_base:
            degraded_notes.append("qwen_chat_not_configured")
        if not self._settings.qwen_rerank_model or not self._settings.qwen_enable_rerank:
            degraded_notes.append("qwen_rerank_not_enabled")

        return CommunityAgentSummaryResponse(
            window=payload.window,
            generated_at=report.generated_at,
            summary_text=summary_text,
            advice=advice,
            analysis=report.analysis,
            charts=charts,
            sources=sources,
            agent_meta=CommunityAgentMeta(
                llm_model=self._settings.qwen_model or self._settings.local_reasoning_model,
                embedding_model=self._settings.qwen_embedding_model,
                rerank_model=self._settings.qwen_rerank_model,
                used_tavily=False,
                used_rerank=False,
                degraded_notes=self._unique_preserve_order(degraded_notes),
            ),
        )

    def tool_query_sensor_history(self, payload: dict[str, object]) -> dict[str, object]:
        window = self._window_from_value(payload.get("window"))
        bucket = self._bucket_from_value(payload.get("bucket"), window=window)
        history = self.get_device_history(
            device_mac=str(payload.get("device_mac") or payload.get("mac_address") or ""),
            window=window,
            bucket=bucket,
        )
        return history.model_dump(mode="json")

    def tool_query_health_scores(self, payload: dict[str, object]) -> dict[str, object]:
        device_mac = str(payload.get("device_mac") or payload.get("mac_address") or "").strip().upper()
        window = self._window_from_value(payload.get("window"))
        start_at, end_at = self._window_range(window)
        scores = self._repository.list_health_scores(
            device_mac=device_mac,
            start_at=start_at,
            end_at=end_at,
        )
        return {
            "device_mac": device_mac,
            "window": window.value,
            "scores": scores,
        }

    def tool_query_alert_history(self, payload: dict[str, object]) -> dict[str, object]:
        window = self._window_from_value(payload.get("window"))
        device_macs = self._normalize_macs(payload.get("device_macs"))
        single_mac = str(payload.get("device_mac") or payload.get("mac_address") or "").strip().upper()
        if single_mac:
            device_macs = [single_mac]
        alarms = self._window_alarms(window=window, device_macs=device_macs)
        return {
            "window": window.value,
            "device_macs": device_macs,
            "alerts": [
                {
                    "id": alarm.id,
                    "device_mac": alarm.device_mac,
                    "alarm_type": alarm.alarm_type.value,
                    "alarm_layer": alarm.alarm_layer.value,
                    "alarm_level": int(alarm.alarm_level.value),
                    "message": alarm.message,
                    "created_at": alarm.created_at.isoformat(),
                    "acknowledged": alarm.acknowledged,
                }
                for alarm in alarms
            ],
        }

    def tool_summarize_window_metrics(self, payload: dict[str, object]) -> dict[str, object]:
        window = self._window_from_value(payload.get("window"))
        report = self.build_window_report(window=window, device_macs=self._normalize_macs(payload.get("device_macs")))
        return report.analysis.model_dump(mode="json")

    def tool_build_chart_payloads(self, payload: dict[str, object]) -> dict[str, object]:
        window = self._window_from_value(payload.get("window"))
        report = self.build_window_report(window=window, device_macs=self._normalize_macs(payload.get("device_macs")))
        return {
            "window": window.value,
            "charts": [chart.model_dump(mode="json") for chart in report.analysis.chart_payloads],
        }

    def tool_query_device_status_history(self, payload: dict[str, object]) -> dict[str, object]:
        device_macs = self._normalize_macs(payload.get("device_macs"))
        single_mac = str(payload.get("device_mac") or payload.get("mac_address") or "").strip().upper()
        if single_mac:
            device_macs = [single_mac]
        start_at, end_at = self._window_range(self._window_from_value(payload.get("window")))
        status_history = self._repository.list_status_history(
            device_macs=device_macs or None,
            start_at=start_at,
            end_at=end_at,
        )
        devices = self._selected_devices(device_macs)
        return {
            "device_macs": [device.mac_address for device in devices],
            "status_history_available": bool(status_history),
            "note": (
                "returning persisted device status history"
                if status_history
                else "no persisted status change found in the window; returning the latest device snapshot"
            ),
            "items": status_history if status_history else [
                {
                    "device_mac": device.mac_address,
                    "status": device.status.value,
                    "bind_status": device.bind_status.value,
                    "user_id": device.user_id,
                    "last_sample_at": (
                        latest.timestamp.isoformat() if (latest := self._stream.latest(device.mac_address)) else None
                    ),
                }
                for device in devices
            ],
        }

    def tool_run_tavily_search(self, payload: dict[str, object]) -> dict[str, object]:
        query = str(payload.get("query") or "").strip()
        if not query:
            return {
                "query": query,
                "status": "invalid",
                "used_tavily": False,
                "results": [],
                "degraded_notes": ["empty_query"],
            }

        degraded_notes: list[str] = []
        results: list[dict[str, object]] = []
        used_tavily = False

        if self._settings.tavily_api_key:
            tavily_result = self._run_tavily_search(query)
            if tavily_result is not None:
                used_tavily = True
                results = tavily_result
            else:
                degraded_notes.append("tavily_request_failed")
        else:
            degraded_notes.append("tavily_not_configured")

        if not results:
            degraded_notes.append("external_search_disabled_without_tavily")

        return {
            "query": query,
            "status": "ok" if results else "degraded",
            "used_tavily": used_tavily,
            "results": results,
            "degraded_notes": degraded_notes,
        }

    def _run_tavily_search(self, query: str) -> list[dict[str, object]] | None:
        body = json.dumps(
            {
                "api_key": self._settings.tavily_api_key,
                "query": query,
                "max_results": 5,
                "search_depth": "basic",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = request.Request(
            url="https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._settings.rag_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None

        results = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": str(item.get("title") or item.get("url") or "web result"),
                    "url": str(item.get("url") or ""),
                    "snippet": str(item.get("content") or item.get("snippet") or "").strip(),
                }
            )
        return results

    def _run_duckduckgo_search(self, query: str) -> list[dict[str, object]]:
        url = "https://api.duckduckgo.com/?" + parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            }
        )
        req = request.Request(url=url, headers={"User-Agent": "aiot-health-agent/1.0"})
        try:
            with request.urlopen(req, timeout=self._settings.rag_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            return []

        results: list[dict[str, object]] = []
        abstract = str(payload.get("AbstractText") or "").strip()
        abstract_url = str(payload.get("AbstractURL") or "").strip()
        abstract_source = str(payload.get("Heading") or payload.get("AbstractSource") or "DuckDuckGo")
        if abstract:
            results.append({"title": abstract_source, "url": abstract_url, "snippet": abstract})

        for item in payload.get("Results", []):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": str(item.get("Text") or item.get("FirstURL") or "web result"),
                    "url": str(item.get("FirstURL") or ""),
                    "snippet": str(item.get("Text") or "").strip(),
                }
            )

        for topic in payload.get("RelatedTopics", []):
            if not isinstance(topic, dict):
                continue
            if "Topics" in topic and isinstance(topic["Topics"], list):
                for nested in topic["Topics"]:
                    if not isinstance(nested, dict):
                        continue
                    results.append(
                        {
                            "title": str(nested.get("Text") or nested.get("FirstURL") or "related topic"),
                            "url": str(nested.get("FirstURL") or ""),
                            "snippet": str(nested.get("Text") or "").strip(),
                        }
                    )
                continue
            results.append(
                {
                    "title": str(topic.get("Text") or topic.get("FirstURL") or "related topic"),
                    "url": str(topic.get("FirstURL") or ""),
                    "snippet": str(topic.get("Text") or "").strip(),
                }
            )
        return results[:8]

    def _build_history_points(
        self,
        samples: list[HealthSample],
        *,
        bucket: HistoryBucket,
    ) -> list[SensorHistoryPoint]:
        ordered = sorted(samples, key=lambda item: item.timestamp)
        if bucket == HistoryBucket.RAW:
            return [
                SensorHistoryPoint(
                    bucket_start=sample.timestamp,
                    bucket_end=None,
                    heart_rate=float(sample.heart_rate),
                    temperature=float(sample.temperature),
                    blood_oxygen=float(sample.blood_oxygen),
                    health_score=float(sample.health_score) if sample.health_score is not None else None,
                    battery=float(sample.battery),
                    steps=float(sample.steps) if sample.steps is not None else None,
                    sos_count=1 if sample.sos_flag else 0,
                    sample_count=1,
                    risk_level=self._analysis.sample_risk_level(sample),
                )
                for sample in ordered
            ]

        grouped: dict[datetime, list[HealthSample]] = defaultdict(list)
        for sample in ordered:
            grouped[self._bucket_start(sample.timestamp, bucket)].append(sample)

        delta = timedelta(hours=1) if bucket == HistoryBucket.HOUR else timedelta(days=1)
        points: list[SensorHistoryPoint] = []
        for start in sorted(grouped):
            batch = grouped[start]
            points.append(
                SensorHistoryPoint(
                    bucket_start=start,
                    bucket_end=start + delta,
                    heart_rate=self._average([float(item.heart_rate) for item in batch]),
                    temperature=self._average([float(item.temperature) for item in batch]),
                    blood_oxygen=self._average([float(item.blood_oxygen) for item in batch]),
                    health_score=self._average(
                        [float(item.health_score) for item in batch if item.health_score is not None]
                    ),
                    battery=self._average([float(item.battery) for item in batch]),
                    steps=self._average([float(item.steps) for item in batch if item.steps is not None]),
                    sos_count=sum(1 for item in batch if item.sos_flag),
                    sample_count=len(batch),
                    risk_level=self._highest_risk_level(
                        [self._analysis.sample_risk_level(item) for item in batch]
                    ),
                )
            )
        return points

    def _build_window_analysis(
        self,
        *,
        window: WindowKind,
        histories: dict[str, list[HealthSample]],
        devices: list[DeviceRecord],
        alarms: list[AlarmRecord],
    ) -> CommunityWindowAnalysis:
        latest_by_device = {mac: samples[-1] for mac, samples in histories.items() if samples}
        visible_macs = {device.mac_address for device in devices}
        start_at, end_at = self._window_range(window)
        active_alarm_counts = Counter(
            alarm.device_mac
            for alarm in self._repository.list_alerts(
                device_macs=sorted(visible_macs) if visible_macs else None,
                start_at=start_at,
                end_at=end_at,
                active_only=True,
            )
        )
        if not active_alarm_counts:
            active_alarm_counts = Counter(
                alarm.device_mac
                for alarm in self._alarm_service.list_alarms(active_only=True)
                if not visible_macs or alarm.device_mac in visible_macs
            )
        elder_by_device = self._elder_name_by_device()

        risk_distribution: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
        device_status_distribution = {"online": 0, "offline": 0, "warning": 0}
        alert_breakdown: dict[str, int] = {}
        high_risk_entities: list[HighRiskEntity] = []
        sample_count = sum(len(batch) for batch in histories.values())

        for alarm_type, count in Counter(alarm.alarm_type.value for alarm in alarms).items():
            alert_breakdown[alarm_type] = count

        for device in devices:
            device_status_distribution[device.status.value] = device_status_distribution.get(device.status.value, 0) + 1
            latest = latest_by_device.get(device.mac_address)
            active_alert_count = active_alarm_counts.get(device.mac_address, 0)
            risk_level = self._device_risk_level(device=device, latest=latest, active_alert_count=active_alert_count)
            risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1
            if risk_level in {"high", "medium"}:
                high_risk_entities.append(
                    HighRiskEntity(
                        device_mac=device.mac_address,
                        elder_name=elder_by_device.get(device.mac_address),
                        risk_level=risk_level,
                        latest_health_score=float(latest.health_score) if latest and latest.health_score is not None else None,
                        active_alert_count=active_alert_count,
                        reasons=self._device_risk_reasons(
                            device=device,
                            latest=latest,
                            active_alert_count=active_alert_count,
                        ),
                    )
                )

        health_scores = [
            float(sample.health_score)
            for sample in latest_by_device.values()
            if sample.health_score is not None
        ]
        blood_oxygen_values = [float(sample.blood_oxygen) for sample in latest_by_device.values()]
        heart_rates = [float(sample.heart_rate) for sample in latest_by_device.values()]
        chart_payloads = self._build_chart_payloads(
            window=window,
            histories=histories,
            devices=devices,
            alarms=alarms,
            risk_distribution=risk_distribution,
            device_status_distribution=device_status_distribution,
            high_risk_entities=high_risk_entities,
        )

        key_metrics = {
            "device_count": len(devices),
            "reported_device_count": len(latest_by_device),
            "sample_count": sample_count,
            "active_alert_count": sum(1 for alarm in alarms if not alarm.acknowledged),
            "window_alert_count": len(alarms),
            "high_risk_device_count": sum(1 for entity in high_risk_entities if entity.risk_level == "high"),
            "average_health_score": round(self._average(health_scores) or 0.0, 1),
            "average_blood_oxygen": round(self._average(blood_oxygen_values) or 0.0, 1),
            "average_heart_rate": round(self._average(heart_rates) or 0.0, 1),
            "online_device_count": device_status_distribution.get(DeviceStatus.ONLINE.value, 0),
            "offline_device_count": device_status_distribution.get(DeviceStatus.OFFLINE.value, 0),
            "warning_device_count": device_status_distribution.get(DeviceStatus.WARNING.value, 0),
            "window": window.value,
        }

        return CommunityWindowAnalysis(
            key_metrics=key_metrics,
            risk_distribution=risk_distribution,
            alert_breakdown=alert_breakdown,
            device_status_distribution=device_status_distribution,
            high_risk_entities=sorted(
                high_risk_entities,
                key=lambda item: (
                    -RISK_ORDER.get(item.risk_level, 0),
                    -item.active_alert_count,
                    item.latest_health_score if item.latest_health_score is not None else 999.0,
                ),
            )[:10],
            trend_findings=self._build_trend_findings(
                window=window,
                devices=devices,
                alarms=alarms,
                risk_distribution=risk_distribution,
                device_status_distribution=device_status_distribution,
                high_risk_entities=high_risk_entities,
                chart_payloads=chart_payloads,
                average_health_score=key_metrics["average_health_score"],
            ),
            chart_payloads=chart_payloads,
        )

    def _build_chart_payloads(
        self,
        *,
        window: WindowKind,
        histories: dict[str, list[HealthSample]],
        devices: list[DeviceRecord],
        alarms: list[AlarmRecord],
        risk_distribution: dict[str, int],
        device_status_distribution: dict[str, int],
        high_risk_entities: list[HighRiskEntity],
    ) -> list[ChartPayload]:
        bucket = HistoryBucket.HOUR if window == WindowKind.DAY else HistoryBucket.DAY
        buckets = self._window_buckets(window)
        labels = [self._bucket_label(item, bucket=bucket) for item in buckets]

        score_series: dict[datetime, list[float]] = defaultdict(list)
        for samples in histories.values():
            for sample in samples:
                if sample.health_score is None:
                    continue
                score_series[self._bucket_start(sample.timestamp, bucket)].append(float(sample.health_score))

        alert_series = Counter(self._bucket_start(alarm.created_at, bucket) for alarm in alarms)
        average_scores = [round(self._average(score_series.get(item, [])) or 0.0, 1) for item in buckets]
        alert_counts = [alert_series.get(item, 0) for item in buckets]

        top_entities = sorted(
            high_risk_entities,
            key=lambda item: (
                -RISK_ORDER.get(item.risk_level, 0),
                -item.active_alert_count,
                item.latest_health_score if item.latest_health_score is not None else 999.0,
            ),
        )[:5]
        top_labels = [entity.elder_name or entity.device_mac for entity in top_entities]
        top_scores = [
            self._entity_priority_score(
                risk_level=entity.risk_level,
                active_alert_count=entity.active_alert_count,
                latest_health_score=entity.latest_health_score,
            )
            for entity in top_entities
        ]

        return [
            ChartPayload(
                id="community_score_trend",
                title="过去窗口平均健康评分趋势",
                type="line",
                echarts_option={
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": labels},
                    "yAxis": {"type": "value", "min": 0, "max": 100},
                    "series": [
                        {
                            "name": "平均健康评分",
                            "type": "line",
                            "smooth": True,
                            "data": average_scores,
                        }
                    ],
                },
                summary="展示过去窗口内各时间桶的平均健康评分变化。",
            ),
            ChartPayload(
                id="community_alert_trend",
                title="过去窗口告警数量趋势",
                type="bar",
                echarts_option={
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": labels},
                    "yAxis": {"type": "value", "minInterval": 1},
                    "series": [
                        {
                            "name": "告警数量",
                            "type": "bar",
                            "data": alert_counts,
                        }
                    ],
                },
                summary="展示过去窗口内告警事件在各时间桶的分布。",
            ),
            ChartPayload(
                id="risk_distribution",
                title="风险分布",
                type="pie",
                echarts_option={
                    "tooltip": {"trigger": "item"},
                    "series": [
                        {
                            "name": "风险分布",
                            "type": "pie",
                            "radius": ["45%", "72%"],
                            "data": [
                                {"name": "高风险", "value": risk_distribution.get("high", 0)},
                                {"name": "中风险", "value": risk_distribution.get("medium", 0)},
                                {"name": "低风险", "value": risk_distribution.get("low", 0)},
                                {"name": "未知", "value": risk_distribution.get("unknown", 0)},
                            ],
                        }
                    ],
                },
                summary="统计当前窗口内高、中、低和未知风险设备的数量。",
            ),
            ChartPayload(
                id="device_online_distribution",
                title="设备在线状态分布",
                type="pie",
                echarts_option={
                    "tooltip": {"trigger": "item"},
                    "series": [
                        {
                            "name": "设备状态",
                            "type": "pie",
                            "radius": "68%",
                            "data": [
                                {
                                    "name": {
                                        "online": "在线",
                                        "offline": "离线",
                                        "warning": "告警"
                                    }.get(key, key), 
                                    "value": value
                                }
                                for key, value in device_status_distribution.items()
                            ],
                        }
                    ],
                },
                summary=f"共统计 {len(devices)} 台设备的在线、离线与告警状态。",
            ),
            ChartPayload(
                id="top_risk_entities",
                title="重点关注对象",
                type="bar",
                echarts_option={
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "value"},
                    "yAxis": {"type": "category", "data": top_labels},
                    "series": [
                        {
                            "name": "优先级得分",
                            "type": "bar",
                            "data": top_scores,
                        }
                    ],
                },
                summary="按综合风险优先级展示最需要值守关注的对象。",
            ),
        ]

    def _build_trend_findings(
        self,
        *,
        window: WindowKind,
        devices: list[DeviceRecord],
        alarms: list[AlarmRecord],
        risk_distribution: dict[str, int],
        device_status_distribution: dict[str, int],
        high_risk_entities: list[HighRiskEntity],
        chart_payloads: list[ChartPayload],
        average_health_score: float,
    ) -> list[str]:
        window_label = "过去一天" if window == WindowKind.DAY else "过去一周"
        findings: list[str] = [
            f"{window_label}纳入 {len(devices)} 台设备，平均健康评分约 {average_health_score:.1f} 分。",
        ]
        if risk_distribution.get("high", 0):
            focus = "、".join(
                item.elder_name or item.device_mac
                for item in sorted(
                    high_risk_entities,
                    key=lambda entity: (
                        -RISK_ORDER.get(entity.risk_level, 0),
                        -entity.active_alert_count,
                    ),
                )[:3]
            )
            findings.append(f"当前识别到 {risk_distribution.get('high', 0)} 台高风险设备，重点关注 {focus}。")
        if alarms:
            top_alarm_type, top_alarm_count = Counter(alarm.alarm_type.value for alarm in alarms).most_common(1)[0]
            findings.append(f"窗口内记录 {len(alarms)} 条告警，其中 {top_alarm_type} 最多，共 {top_alarm_count} 条。")
        if device_status_distribution.get("offline", 0):
            findings.append(
                f"有 {device_status_distribution.get('offline', 0)} 台设备处于离线状态，建议优先排查采集链路和设备电量。"
            )
        score_chart = next((chart for chart in chart_payloads if chart.id == "community_score_trend"), None)
        if score_chart:
            series = score_chart.echarts_option.get("series", [])
            if isinstance(series, list) and series:
                values = series[0].get("data", [])
                if isinstance(values, list) and len(values) >= 2:
                    start = float(values[0] or 0.0)
                    end = float(values[-1] or 0.0)
                    delta = round(end - start, 1)
                    if abs(delta) >= 3:
                        direction = "上升" if delta > 0 else "下降"
                        findings.append(f"平均健康评分在窗口内整体呈{direction}趋势，首尾变化约 {abs(delta):.1f} 分。")
        return findings[:5]

    def _build_summary_text(
        self,
        *,
        question: str,
        window: WindowKind,
        analysis: CommunityWindowAnalysis,
        advice: list[str],
    ) -> str:
        del question

        metrics = analysis.key_metrics
        window_label = "过去一天" if window == WindowKind.DAY else "过去一周"
        reported_count = int(metrics.get("reported_device_count", 0) or 0)
        device_count = int(metrics.get("device_count", 0) or 0)
        high_count = int(analysis.risk_distribution.get("high", 0) or 0)
        medium_count = int(analysis.risk_distribution.get("medium", 0) or 0)
        avg_score = float(metrics.get("average_health_score", 0.0) or 0.0)
        alert_count = int(metrics.get("window_alert_count", 0) or 0)
        lead_finding = analysis.trend_findings[0] if analysis.trend_findings else ""
        lead_advice = advice[0] if advice else "保持常规巡检并持续观察趋势变化。"

        return (
            f"{window_label}共覆盖 {device_count} 台设备，其中 {reported_count} 台有有效监测数据。"
            f" 当前高风险设备 {high_count} 台，中风险设备 {medium_count} 台，平均健康评分 {avg_score:.1f} 分，"
            f"窗口内累计告警 {alert_count} 条。"
            f"{lead_finding} 建议优先执行：{lead_advice}"
        ).strip()

    def _build_summary_advice(self, analysis: CommunityWindowAnalysis) -> list[str]:
        metrics = analysis.key_metrics
        advice: list[str] = []
        high_risk_entities = analysis.high_risk_entities

        if high_risk_entities:
            focus = "、".join(
                entity.elder_name or entity.device_mac for entity in high_risk_entities[:3]
            )
            advice.append(f"优先复核 {focus} 的最新生命体征、现场状态和未确认告警。")
        if int(metrics.get("offline_device_count", 0) or 0) > 0:
            advice.append("尽快排查离线设备的网关连接、佩戴状态和电量，避免关键时段缺数。")
        if int(metrics.get("window_alert_count", 0) or 0) > 0:
            advice.append("结合告警分布安排分级随访，优先处理 SOS、血氧偏低和持续高温相关事件。")
        if float(metrics.get("average_health_score", 0.0) or 0.0) < 75:
            advice.append("建议在下一轮巡检中重点关注健康评分偏低对象，并复测关键指标。")
        if not advice:
            advice.append("社区整体态势相对平稳，可维持常规巡检节奏并持续观察异常漂移。")
        return advice[:4]

    def _knowledge_sources(
        self,
        *,
        question: str,
        analysis: CommunityWindowAnalysis,
        include_web_search: bool,
    ) -> tuple[list[AgentSourceItem], list[str]]:
        query = " ".join(
            part
            for part in [
                question,
                "community elder care risk follow-up intervention guidance",
                *(entity.reasons[0] for entity in analysis.high_risk_entities[:3] if entity.reasons),
                *(analysis.trend_findings[:2]),
            ]
            if part
        ).strip()
        hits = self._rag.search(query, top_k=self._settings.rag_top_k, network_online=False, allow_rerank=False)
        degraded_notes: list[str] = []
        if not hits:
            degraded_notes.append("knowledge_base_no_hits")
        if include_web_search and not self._settings.tavily_api_key:
            degraded_notes.append("web_search_requested_but_unavailable")

        return (
            [self._parse_kb_hit(hit) for hit in hits[: self._settings.rag_top_k]],
            degraded_notes,
        )

    def _parse_kb_hit(self, hit: str) -> AgentSourceItem:
        normalized = hit.strip()
        if normalized.startswith("[") and "]" in normalized:
            source, snippet = normalized[1:].split("]", maxsplit=1)
            title = source.strip() or "knowledge-base"
            return AgentSourceItem(
                source_type="knowledge_base",
                title=title,
                url=None,
                snippet=snippet.strip()[:320],
            )
        return AgentSourceItem(
            source_type="knowledge_base",
            title="knowledge-base",
            url=None,
            snippet=normalized[:320],
        )

    def _selected_devices(self, device_macs: list[str]) -> list[DeviceRecord]:
        devices = self._device_service.list_devices()
        if not device_macs:
            return devices
        visible = set(device_macs)
        return [device for device in devices if device.mac_address in visible]

    def _window_alarms(self, *, window: WindowKind, device_macs: list[str]) -> list[AlarmRecord]:
        start_at, end_at = self._window_range(window)
        alarms = self._repository.list_alerts(
            device_macs=device_macs or None,
            start_at=start_at,
            end_at=end_at,
            active_only=False,
        )
        if alarms:
            return alarms
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._window_minutes(window))
        visible = set(device_macs)
        return [
            alarm
            for alarm in self._alarm_service.list_alarms(active_only=False)
            if alarm.created_at >= cutoff and (not visible or alarm.device_mac in visible)
        ]

    def _elder_name_by_device(self) -> dict[str, str]:
        directory = self._care_service.get_directory()
        elder_by_device: dict[str, str] = {}
        for elder in directory.elders:
            macs = list(elder.device_macs) or ([elder.device_mac] if elder.device_mac else [])
            for mac in macs:
                elder_by_device[mac.upper()] = elder.name
        return elder_by_device

    def _device_risk_level(
        self,
        *,
        device: DeviceRecord,
        latest: HealthSample | None,
        active_alert_count: int,
    ) -> str:
        if latest is None:
            if device.status == DeviceStatus.OFFLINE:
                return "high"
            return "unknown"
        risk_level = self._analysis.sample_risk_level(latest)
        if active_alert_count >= 2 and risk_level == "medium":
            return "high"
        return risk_level

    def _device_risk_reasons(
        self,
        *,
        device: DeviceRecord,
        latest: HealthSample | None,
        active_alert_count: int,
    ) -> list[str]:
        reasons: list[str] = []
        if device.status == DeviceStatus.OFFLINE:
            reasons.append("设备当前离线")
        if active_alert_count:
            reasons.append(f"存在 {active_alert_count} 条未确认告警")
        if latest is None:
            reasons.append("当前窗口内暂无有效监测数据")
            return reasons
        if latest.sos_flag:
            reasons.append("检测到 SOS 求助信号")
        if latest.health_score is not None and latest.health_score <= 60:
            reasons.append(f"最新健康评分偏低（{latest.health_score}）")
        if latest.blood_oxygen < 93:
            reasons.append(f"血氧偏低（{latest.blood_oxygen}%）")
        if latest.temperature >= 37.5:
            reasons.append(f"体温偏高（{latest.temperature:.1f}℃）")
        if latest.heart_rate < 50 or latest.heart_rate > 110:
            reasons.append(f"心率异常（{latest.heart_rate} bpm）")
        if not reasons:
            reasons.append("近期生命体征存在波动，建议继续观察")
        return reasons[:4]

    def _window_minutes(self, window: WindowKind) -> int:
        return 24 * 60 if window == WindowKind.DAY else 7 * 24 * 60

    def _window_range(self, window: WindowKind) -> tuple[datetime, datetime]:
        end_at = datetime.now(timezone.utc)
        start_at = end_at - timedelta(minutes=self._window_minutes(window))
        return start_at, end_at

    def _sample_limit(self, window: WindowKind) -> int:
        return 2048 if window == WindowKind.DAY else 8192

    def _window_buckets(self, window: WindowKind) -> list[datetime]:
        now = datetime.now(timezone.utc)
        if window == WindowKind.DAY:
            current = now.replace(minute=0, second=0, microsecond=0)
            start = current - timedelta(hours=23)
            return [start + timedelta(hours=index) for index in range(24)]
        current = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = current - timedelta(days=6)
        return [start + timedelta(days=index) for index in range(7)]

    def _bucket_start(self, timestamp: datetime, bucket: HistoryBucket) -> datetime:
        value = timestamp.astimezone(timezone.utc)
        if bucket == HistoryBucket.DAY:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        if bucket == HistoryBucket.HOUR:
            return value.replace(minute=0, second=0, microsecond=0)
        return value

    def _bucket_label(self, value: datetime, *, bucket: HistoryBucket) -> str:
        if bucket == HistoryBucket.DAY:
            return value.strftime("%m-%d")
        return value.strftime("%m-%d %H:00")

    def _window_from_value(self, value: object) -> WindowKind:
        if isinstance(value, WindowKind):
            return value
        try:
            return WindowKind(str(value or WindowKind.DAY.value))
        except ValueError:
            return WindowKind.DAY

    def _bucket_from_value(self, value: object, *, window: WindowKind) -> HistoryBucket:
        if isinstance(value, HistoryBucket):
            return value
        fallback = HistoryBucket.HOUR if window == WindowKind.DAY else HistoryBucket.DAY
        try:
            return HistoryBucket(str(value or fallback.value))
        except ValueError:
            return fallback

    def _normalize_macs(self, values: object) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            parts = [item.strip().upper() for item in values.split(",")]
            return [item for item in parts if item]
        if isinstance(values, (list, tuple, set)):
            return [str(item).strip().upper() for item in values if str(item).strip()]
        return []

    def _highest_risk_level(self, values: list[str]) -> str:
        return max(values or ["unknown"], key=lambda item: RISK_ORDER.get(item, 0))

    def _entity_priority_score(
        self,
        *,
        risk_level: str,
        active_alert_count: int,
        latest_health_score: float | None,
    ) -> int:
        score = RISK_ORDER.get(risk_level, 0) * 40 + min(active_alert_count, 5) * 12
        if latest_health_score is not None:
            score += max(0, int(round(100 - latest_health_score)))
        return score

    @staticmethod
    def _average(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _unique_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered
