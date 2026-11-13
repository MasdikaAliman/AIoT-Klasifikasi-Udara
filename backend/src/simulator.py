import sys
import time
import json
import datetime
import os
import random
import pandas as pd
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "engine_room/sensor")

# Locate dataset Excel
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
excel_path = os.path.join(root_dir, 'docs', 'CONFINED_SPACE_CLASSIFIED.xlsx')

def load_simulation_data():
    if os.path.exists(excel_path):
        try:
            print(f"Loading dataset from: {excel_path}")
            df_raw = pd.read_excel(excel_path, header=None)
            data_rows = df_raw.iloc[2:].copy()
            data_rows.columns = [
                'vessel_ship', 'location_work', 'date', 'session', 'time',
                'o2', 'o2_desc', 'co', 'co_desc', 'air_quality',
                'o2_class_computed', 'co_class_computed', 'col12', 'col13'
            ]
            df = data_rows[['vessel_ship', 'location_work', 'o2', 'co']].dropna()
            df['o2'] = pd.to_numeric(df['o2'], errors='coerce')
            df['co'] = pd.to_numeric(df['co'], errors='coerce')
            return df.dropna().to_dict(orient='records')
        except Exception as e:
            print(f"Error loading Excel: {e}. Falling back to default data.")
    
    # Fallback default dataset
    return [
        {"vessel_ship": "LNG (HYUNDAI OCEANPIA)", "location_work": "ENGINE PUMP ROOM", "o2": 20.8, "co": 5},
        {"vessel_ship": "NINGGALO VISION", "location_work": "RUDDER BLADE", "o2": 19.4, "co": 18},
        {"vessel_ship": "ASGARD", "location_work": "CYLINDER HYDRAULIC", "o2": 19.0, "co": 30}
    ]

def run_simulator(mode="dummy"):
    client = mqtt.Client()
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        
    status_topic = MQTT_TOPIC + "/status"
    # Set Last Will and Testament (LWT)
    client.will_set(status_topic, payload=json.dumps({"status": "offline"}), qos=1, retain=True)
    
    try:
        print(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        # Publish online status immediately as retained message
        client.publish(status_topic, payload=json.dumps({"status": "online"}), qos=1, retain=True)
        print("Connected successfully and published online status.")
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return

    dataset = []
    if mode == "dataset":
        dataset = load_simulation_data()
        print(f"Loaded {len(dataset)} records for simulation.")

    i = 0
    try:
        while True:
            try:
                if mode == "dataset" and dataset:
                    record = dataset[i % len(dataset)]
                    payload = {
                        "vessel_ship": record["vessel_ship"],
                        "location_work": record["location_work"],
                        "o2": float(record["o2"]),
                        "co": float(record["co"]),
                        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
                    }
                    i += 1
                else:
                    # Dummy Mode: Random walk with occasional danger spikes
                    o2 = round(random.uniform(19.0, 21.0), 2)
                    # Normal CO level is 0-5, spike sometimes up to 35
                    co = random.choice([random.randint(0, 5), random.randint(0, 5), random.randint(10, 35)])
                    payload = {
                        "vessel_ship": "SIMULATED_VESSEL_01",
                        "location_work": "ENGINE_PUMP_ROOM",
                        "o2": o2,
                        "co": co,
                        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
                    }

                client.publish(MQTT_TOPIC, json.dumps(payload))
                print(f"[{mode.upper()} MODE] Published: {payload}")
            except Exception as e:
                print(f"Failed to publish message: {e}")
                
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nStopping simulator...")
    finally:
        # Publish offline status on exit
        try:
            print("Publishing offline status...")
            client.publish(status_topic, payload=json.dumps({"status": "offline"}), qos=1, retain=True)
            client.disconnect()
        except Exception as e:
            print(f"Failed to publish offline status on exit: {e}")

if __name__ == "__main__":
    sim_mode = "dummy"
    if len(sys.argv) > 1:
        sim_mode = sys.argv[1].strip().lower()
        if sim_mode not in ["dummy", "dataset"]:
            sim_mode = "dummy"
            
    run_simulator(sim_mode)
