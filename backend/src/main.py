import json
import os
import time
import math
import threading
from datetime import datetime, timedelta
from typing import List, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
import pandas as pd
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from database import init_db, get_db, AirQualityLog, SessionLocal, AirQualityStatus
from knn_classifier import predict_air_quality

def safe_float(val: Any, default: float) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default

def safe_str(val: Any, default: str) -> str:
    if val is None or not str(val).strip():
        return default
    return str(val).strip()

app = FastAPI(title="AIoT Air Quality Classifier")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# Throttled database saving states
last_save_time = datetime.min
last_class = ""
SAVE_INTERVAL = timedelta(seconds=int(os.getenv("SAVE_INTERVAL_SECONDS", "30")))

# Connection and activity statuses
latest_sensor_data = None
mqtt_connected = False
last_message_time = 0.0
device_active = False

def on_message(client, userdata, msg):
    global last_save_time, last_class, last_message_time, latest_sensor_data, mqtt_connected, device_active
    mqtt_connected = True
    # Handle Last Will and Testament (LWT) status updates
    status_topic = f'{os.getenv("MQTT_TOPIC", "engine_room/sensor")}/status'
    if msg.topic == status_topic:
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            device_active = (payload.get("status") == "online")
            print(f"ESP32 Status Update (LWT): {'ONLINE' if device_active else 'OFFLINE'}")
        except Exception:
            pass
        return

    # Normal sensor data
    last_message_time = time.time()
    device_active = True
    try:
        raw_payload = msg.payload.decode('utf-8', errors='ignore')
        payload = json.loads(raw_payload)

        # Ignore if payload is not a JSON object
        if not isinstance(payload, dict):
            print(f"Skipping non-dict MQTT payload on [{msg.topic}]: {raw_payload}")
            return

        o2 = safe_float(payload.get("o2"), 20.9)
        co = safe_float(payload.get("co"), 0.0)
        vessel = safe_str(payload.get("vessel_ship"), "SIMULATED_VESSEL_01")
        location = safe_str(payload.get("location_work"), "ENGINE_PUMP_ROOM")

        # KNN prediction
        knn_class = predict_air_quality(o2, co)
        now = datetime.utcnow()

        # Database save conditions (Time interval OR state transition)
        time_elapsed = now - last_save_time >= SAVE_INTERVAL
        status_changed = knn_class != last_class

        if time_elapsed or status_changed:
            db = SessionLocal()
            try:
                log = AirQualityLog(
                    vessel_ship=vessel,
                    location_work=location,
                    o2=o2,
                    co=co,
                    knn_class=AirQualityStatus[knn_class],
                    timestamp=now
                )
                db.add(log)
                db.commit()
                last_save_time = now
                last_class = knn_class
                print(f"Logged to Database: {vessel} - {knn_class} (Trigger: time={time_elapsed}, status={status_changed})")
            finally:
                db.close()

        # Update latest sensor data state for broadcasting
        broadcast_data = {
            "vessel_ship": vessel,
            "location_work": location,
            "o2": o2,
            "co": co,
            "knn_class": knn_class,
            "timestamp": now.isoformat() + "Z"
        }
        latest_sensor_data = broadcast_data

        # Publish alarm action back to ESP32
        action_map = {"Safe": 1, "Aware": 2, "Danger": 3}
        action_level = action_map.get(knn_class, 1)
        action_topic = os.getenv("MQTT_ACTION_TOPIC", "engine_room/action")
        try:
            action_payload = json.dumps({
                "action": action_level,
                "status": knn_class,
                "knn_class": knn_class,
                "vessel_ship": vessel,
                "location_work": location,
                "timestamp": now.isoformat() + "Z"
            })
            client.publish(action_topic, action_payload)
        except Exception as e_pub:
            print(f"Error publishing MQTT alarm action: {e_pub}")
    except Exception as e:
        raw_preview = msg.payload.decode('utf-8', errors='ignore')[:150]
        print(f"Error handling MQTT message on [{msg.topic}]: {e} | Payload: {raw_preview}")

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print("Connected to MQTT Broker successfully.")
        base_topic = os.getenv("MQTT_TOPIC", "engine_room/sensor")
        client.subscribe(base_topic)
        client.subscribe(f"{base_topic}/status")
    else:
        mqtt_connected = False
        print(f"MQTT connection failed with code {rc}")

def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    print(f"MQTT Client disconnected (code: {rc}). Reconnecting in background...")
    while True:
        try:
            client.reconnect()
            break
        except Exception as e:
            print(f"Reconnection failed: {e}. Retrying in 5s...")
            time.sleep(5)

def start_mqtt_client():
    client = mqtt.Client()
    broker = os.getenv("MQTT_BROKER", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    user = os.getenv("MQTT_USER", "")
    password = os.getenv("MQTT_PASS", "")
    
    if user and password:
        client.username_pw_set(user, password)
    
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    while True:
        try:
            print(f"Connecting to MQTT Broker at {broker}:{port}...")
            client.connect(broker, port, 60)
            client.loop_forever()
            break
        except Exception as e:
            print(f"Initial MQTT connection failed: {e}. Retrying in 5s...")
            time.sleep(5)

async def status_broadcaster():
    global latest_sensor_data, mqtt_connected, device_active
    import asyncio
    while True:
        try:
            status_data = {
                "type": "status",
                "mqtt_connected": mqtt_connected,
                "device_active": device_active,
                "latest_data": latest_sensor_data
            }
            await manager.broadcast(status_data)
        except Exception as e:
            print(f"Error in status broadcaster: {e}")
        await asyncio.sleep(2)

@app.on_event("startup")
def startup():
    init_db()
    import asyncio
    manager.loop = asyncio.get_event_loop()
    manager.loop.create_task(status_broadcaster())
    # Start MQTT background thread
    threading.Thread(target=start_mqtt_client, daemon=True).start()

@app.get("/api/logs")
def api_get_logs(db: Session = Depends(get_db)):
    logs = db.query(AirQualityLog).order_by(AirQualityLog.timestamp.desc()).limit(50).all()
    # Format Enum values to simple strings for API consumption
    return [
        {
            "id": log.id,
            "vessel_ship": log.vessel_ship,
            "location_work": log.location_work,
            "o2": log.o2,
            "co": log.co,
            "knn_class": log.knn_class.value,
            "timestamp": log.timestamp.isoformat() + "Z"
        } for log in logs
    ]

@app.get("/api/logs/download")
def api_download_excel(start_time: str = None, end_time: str = None, timezone_offset: int = 0, db: Session = Depends(get_db)):
    import io
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    from datetime import timedelta

    def parse_datetime(dt_str: str):
        if not dt_str:
            return None
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1]
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            raise HTTPException(status_code=400, detail=f"Format tanggal salah: {dt_str}")

    start_dt = parse_datetime(start_time)
    end_dt = parse_datetime(end_time)

    query = db.query(AirQualityLog)
    if start_dt:
        query = query.filter(AirQualityLog.timestamp >= start_dt)
    if end_dt:
        query = query.filter(AirQualityLog.timestamp <= end_dt)

    logs = query.order_by(AirQualityLog.timestamp.asc()).all()

    from utils.excel_generator import generate_styled_excel
    
    output, filename = generate_styled_excel(logs, timezone_offset, start_dt, end_dt)

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Access-Control-Expose-Headers': 'Content-Disposition'
    }
    return StreamingResponse(
        output,
        headers=headers,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.websocket("/ws/air-quality")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=backend_port, reload=True)
