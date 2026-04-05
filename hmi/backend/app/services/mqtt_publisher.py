from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from paho.mqtt import client as mqtt

from app.core.config import settings


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

        if not self.enabled():
            return PublishResult(topic=topic, payload=payload, enabled=False)

        client_id = f"{settings.mqtt_client_id_prefix}-{uuid.uuid4().hex[:8]}"
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)
        try:
            client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=20)
            result = client.publish(
                topic,
                payload=payload,
                qos=max(0, min(2, int(settings.mqtt_publish_qos))),
                retain=settings.mqtt_publish_retain,
            )
            result.wait_for_publish()
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

        return PublishResult(topic=topic, payload=payload, enabled=True)
