from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from paho.mqtt import client as mqtt

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    topic: str
    payload: str
    enabled: bool


class MqttPublisher:
    def enabled(self) -> bool:
        return settings.mqtt_publish_enabled

    def publish_params_set(
        self,
        *,
        device_id: str,
        target_temp_c: float | None,
        kp: float | None,
        ki: float | None,
        kd: float | None,
        control_mode: str | None,
        control_period_ms: int | None,
        apply_immediately: bool = True,
    ) -> PublishResult:
        topic = settings.mqtt_params_set_topic_template.format(device_id=device_id)
        payload_obj = {
            "target_temp_c": target_temp_c,
            "kp": kp,
            "ki": ki,
            "kd": kd,
            "control_mode": control_mode,
            "control_period_ms": control_period_ms,
            "apply_immediately": apply_immediately,
            "source": "hmi",
            "requested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        payload_obj = {k: v for k, v in payload_obj.items() if v is not None}
        payload = json.dumps(payload_obj, ensure_ascii=True, separators=(",", ":"))
        return self.publish_raw(topic=topic, payload=payload)

    def publish_json(self, *, topic: str, payload_obj: dict) -> PublishResult:
        payload = json.dumps(payload_obj, ensure_ascii=True, separators=(",", ":"))
        return self.publish_raw(topic=topic, payload=payload)

    def publish_raw(self, *, topic: str, payload: str) -> PublishResult:
        if not self.enabled():
            return PublishResult(topic=topic, payload=payload, enabled=False)

        client_id = f"{settings.mqtt_client_id_prefix}-{uuid.uuid4().hex[:8]}"
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)
        connect_t0 = time.monotonic()
        try:
            logger.warning(
                "[APPLY-MQTT] connect_start host=%s port=%s client_id=%s topic=%s",
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
                client_id,
                topic,
            )
            client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=20)
            client.loop_start()
            logger.warning(
                "[APPLY-MQTT] connect_done client_id=%s elapsed_ms=%s",
                client_id,
                int((time.monotonic() - connect_t0) * 1000),
            )
            publish_t0 = time.monotonic()
            result = client.publish(
                topic,
                payload=payload,
                qos=max(0, min(2, int(settings.mqtt_publish_qos))),
                retain=settings.mqtt_publish_retain,
            )
            logger.warning(
                "[APPLY-MQTT] publish_sent client_id=%s mid=%s qos=%s",
                client_id,
                getattr(result, "mid", None),
                max(0, min(2, int(settings.mqtt_publish_qos))),
            )
            result.wait_for_publish(timeout=3.0)
            published = result.is_published()
            logger.warning(
                "[APPLY-MQTT] publish_wait_done client_id=%s published=%s rc=%s elapsed_ms=%s",
                client_id,
                published,
                result.rc,
                int((time.monotonic() - publish_t0) * 1000),
            )
            if not published:
                raise HTTPException(status_code=504, detail="MQTT publish timeout")
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise HTTPException(status_code=502, detail=f"MQTT publish failed rc={result.rc}")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"MQTT publish failed: {exc}") from exc
        finally:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            try:
                client.loop_stop()
            except Exception:  # noqa: BLE001
                pass

        return PublishResult(topic=topic, payload=payload, enabled=True)
