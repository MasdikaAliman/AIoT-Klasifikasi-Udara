#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <esp_task_wdt.h>       // Watchdog Timer ESP32
#include <esp_idf_version.h>     // Kompatibilitas versi core ESP32 (v2.x & v3.x)
#include "const_pin.h"

// =====================================================
// Watchdog Timer Configuration
// =====================================================
#define WDT_TIMEOUT_SECONDS 15  // Reboot otomatis jika loop hang > 15 detik

// =====================================================
// WiFi Configuration
// =====================================================

const char* WIFI_SSID = "DIKA";
const char* WIFI_PASSWORD = "30101973";

// =====================================================
// MQTT Configuration
// =====================================================

const char* MQTT_BROKER = "broker.hivemq.com";
const int MQTT_PORT = 1883;

// Telemetry & LWT Status
const char* MQTT_TOPIC = "engine_room/sensor";
const char* MQTT_STATUS_TOPIC = "engine_room/sensor/status";

const char* MQTT_ACTION_TOPIC = "engine_room/action";

// Optional MQTT authentication
const char* MQTT_USER = "";
const char* MQTT_PASS = "";

const char* MQTT_CLIENT_ID = "esp32-engine-room-01";

// =====================================================
// NTP Server (UTC Timestamp)
// =====================================================

const char* NTP_SERVER = "pool.ntp.org";

// =====================================================
// Alarm Levels & Definitions
// =====================================================
//  0 = NONE    -> Lampu hijau OFF,   Buzzer OFF (Standby)
//  1 = SAFE    -> Lampu hijau ON,    Buzzer OFF
//  2 = WARNING -> Lampu hijau Kedip, Buzzer Beep Pendek tiap 2 detik
//  3 = DANGER  -> Lampu hijau OFF,   Buzzer ON (Siren / Bahaya Gas)

enum AlarmLevel {
  ALARM_NONE = 0,
  ALARM_SAFE = 1,
  ALARM_WARNING = 2,
  ALARM_DANGER = 3
};

AlarmLevel alarmLevel = ALARM_NONE;

// Status & Failsafe Watchdog
unsigned long lastActionReceived = 0;
const unsigned long FAILSAFE_TIMEOUT_MS = 20000; // 20 detik tanpa MQTT action -> mode threshold lokal
bool enableFailsafe = true;

// =====================================================
// Hardware Objects
// =====================================================

DFRobot_OxygenSensor oxygen;
MQ7 mq7(MQ7_ANALOG, VOLTAGE);

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// =====================================================
// Helper: Indikator Kedipan Lampu (Relay Green)
// =====================================================

void blinkLamp(int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(RELAY_GREEN, HIGH);
    delay(onMs);
    digitalWrite(RELAY_GREEN, LOW);
    if (i < times - 1) {
      delay(offMs);
    }
  }
}

// =====================================================
// Watchdog Timer Initialization
// =====================================================

void initWatchdog() {
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
  // ESP32 Arduino Core v3.x (ESP-IDF v5+)
  esp_task_wdt_config_t wdt_config = {
      .timeout_ms = WDT_TIMEOUT_SECONDS * 1000,
      .idle_core_mask = 0,
      .trigger_panic = true
  };
  if (esp_task_wdt_init(&wdt_config) != ESP_OK) {
    esp_task_wdt_reconfigure(&wdt_config);
  }
  esp_task_wdt_add(NULL); // Daftarkan task loop() saat ini
#else
  // ESP32 Arduino Core v2.x (ESP-IDF v4+)
  esp_task_wdt_init(WDT_TIMEOUT_SECONDS, true);
  esp_task_wdt_add(NULL); // Daftarkan task loop() saat ini
#endif
  Serial.printf("[WDT] Watchdog Timer aktif (%d detik)\n", WDT_TIMEOUT_SECONDS);
}

// =====================================================
// Helper: Konversi teks status / string ke AlarmLevel
// =====================================================

AlarmLevel parseAlarmLevel(String str) {
  str.trim();
  str.toUpperCase();

  // Angka
  if (str == "1") return ALARM_SAFE;
  if (str == "2") return ALARM_WARNING;
  if (str == "3") return ALARM_DANGER;
  if (str == "0") return ALARM_NONE;

  // Nama kelas
  if (str == "SAFE" || str == "\"SAFE\"" || str == "AMAN") return ALARM_SAFE;
  if (str == "WARNING" || str == "\"WARNING\"" || str == "AWARE" || str == "\"AWARE\"" || str == "WASPADA") return ALARM_WARNING;
  if (str == "DANGER" || str == "\"DANGER\"" || str == "BAHAYA") return ALARM_DANGER;
  if (str == "OFF" || str == "NONE") return ALARM_NONE;

  return ALARM_NONE;
}

// =====================================================
// Alarm Output Driver (Non-blocking, dipanggil terus di loop)
// =====================================================

void updateAlarm() {
  unsigned long now = millis();

  switch (alarmLevel) {
    case ALARM_SAFE:
      // Status Aman: Lampu Hijau Solid Menyala, Buzzer Senyap
      digitalWrite(RELAY_GREEN, HIGH);
      digitalWrite(RELAY_BUZZER, LOW);
      break;

    case ALARM_WARNING:
      // Status Waspada: Lampu Hijau Kedip, Buzzer beep pendek
      digitalWrite(RELAY_GREEN, (now % 1500) < 500 ? HIGH : LOW);
      digitalWrite(RELAY_BUZZER, (now % 2500) < 200 ? HIGH : LOW);
      break;

    case ALARM_DANGER:
      // Status Bahaya Gas: Lampu Hijau Mati, Buzzer Alarm ON terus-menerus
      digitalWrite(RELAY_GREEN, LOW);
      digitalWrite(RELAY_BUZZER, HIGH);
      break;

    case ALARM_NONE:
    default:
      // Kondisi standby / belum ada status aktif
      digitalWrite(RELAY_GREEN, LOW);
      digitalWrite(RELAY_BUZZER, LOW);
      break;
  }
}

// =====================================================
// MQTT Callback (Penerima Kontrol Alarm Action)
// =====================================================

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, MQTT_ACTION_TOPIC) != 0) {
    return;
  }

  char msg[256];
  size_t n = length < (sizeof(msg) - 1) ? length : (sizeof(msg) - 1);
  memcpy(msg, payload, n);
  msg[n] = '\0';

  Serial.print("[MQTT ACTION RX] Topic: ");
  Serial.print(topic);
  Serial.print(" | Payload: ");
  Serial.println(msg);

  int level = -1;

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, msg);

  if (err == DeserializationError::Ok && doc.is<JsonObject>()) {
    if (doc["action"].is<int>()) {
      level = doc["action"].as<int>();
    } else if (doc["action"].is<const char*>()) {
      level = parseAlarmLevel(String(doc["action"].as<const char*>()));
    } else if (doc["alarm"].is<int>()) {
      level = doc["alarm"].as<int>();
    } else if (doc["alarm"].is<const char*>()) {
      level = parseAlarmLevel(String(doc["alarm"].as<const char*>()));
    } else if (doc["status"].is<const char*>()) {
      level = parseAlarmLevel(String(doc["status"].as<const char*>()));
    } else if (doc["knn_class"].is<const char*>()) {
      level = parseAlarmLevel(String(doc["knn_class"].as<const char*>()));
    }
  } else {
    level = parseAlarmLevel(String(msg));
  }

  if (level < 0 || level > 3) {
    Serial.println("[ERROR] Nilai action tidak valid! Diterima format yang tidak dikenal.");
    return;
  }

  alarmLevel = (AlarmLevel)level;
  lastActionReceived = millis();

  const char* names[] = { "NONE (OFF)", "SAFE", "WARNING / AWARE", "DANGER" };
  Serial.print("[ALARM ACTION] Level diperbarui -> ");
  Serial.println(names[alarmLevel]);
}

// =====================================================
// Connect WiFi (dengan Lamp Indicator)
// =====================================================

void connectWiFi() {
  Serial.print("Menghubungkan ke WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 20000) {
    // Indikator lampu berkedip halus saat mencoba menghubungkan ke WiFi
    digitalWrite(RELAY_GREEN, HIGH);
    delay(400);
    digitalWrite(RELAY_GREEN, LOW);
    delay(400);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi terhubung!");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    // Indikator 2x kedipan cepat tanda WiFi sukses tersambung
    blinkLamp(2, 300, 300);
  } else {
    Serial.println("\nGagal terhubung ke WiFi dalam 20 detik, melanjutkan setup...");
    // Indikator 1x kedipan panjang tanda koneksi WiFi belum berhasil
    blinkLamp(1, 800, 200);
  }
}

// =====================================================
// Get ISO8601 UTC timestamp
// =====================================================

String getTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 100)) {
    return "1970-01-01T00:00:00Z";
  }

  char buffer[30];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(buffer);
}

// =====================================================
// Connect MQTT (Non-blocking retry di loop)
// =====================================================

bool connectMQTT() {
  Serial.print("Menghubungkan ke MQTT Broker...");

  bool connected = false;
  const char* lwtPayload = "{\"status\":\"offline\"}";

  if (strlen(MQTT_USER) > 0) {
    connected = mqttClient.connect(
      MQTT_CLIENT_ID,
      MQTT_USER,
      MQTT_PASS,
      MQTT_STATUS_TOPIC,
      1,
      true,
      lwtPayload
    );
  } else {
    connected = mqttClient.connect(
      MQTT_CLIENT_ID,
      MQTT_STATUS_TOPIC,
      1,
      true,
      lwtPayload
    );
  }

  if (connected) {
    Serial.println(" Berhasil terhubung!");
    mqttClient.publish(MQTT_STATUS_TOPIC, "{\"status\":\"online\"}", true);
    mqttClient.subscribe(MQTT_ACTION_TOPIC);
    Serial.print("Berhasil Subscribe topik action: ");
    Serial.println(MQTT_ACTION_TOPIC);
  } else {
    Serial.print(" Gagal, rc=");
    Serial.println(mqttClient.state());
  }

  return connected;
}

// =====================================================
// Maintenance Connection
// =====================================================

void maintainConnections() {
  static unsigned long lastWifiTry = 0;
  static unsigned long lastMqttTry = 0;

  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifiTry >= 10000) {
      lastWifiTry = millis();
      Serial.println("WiFi terputus, mencoba rekoneksi...");
      WiFi.reconnect();
    }
    return;
  }

  if (!mqttClient.connected()) {
    if (millis() - lastMqttTry >= 5000) {
      lastMqttTry = millis();
      connectMQTT();
    }
  }
}

// =====================================================
// Pembacaan Sensor
// =====================================================

float readO2() {
  float oxygenData = oxygen.getOxygenData(COLLECT_NUMBER);
  if (isnan(oxygenData) || isinf(oxygenData) || oxygenData <= 0.0f) {
    Serial.println("[WARNING] Sensor O2 membaca NaN atau unready! Menggunakan fallback 20.9 %vol");
    oxygenData = 20.9f;
  }
  Serial.print("Konsentrasi O2: ");
  Serial.print(oxygenData);
  Serial.println(" %vol");
  return oxygenData;
}

float readCO() {
  float ppm = mq7.readPpm();
  if (isnan(ppm) || isinf(ppm) || ppm < 0.0f) {
    Serial.println("[WARNING] Sensor MQ7 membaca NaN atau unready! Menggunakan fallback 0.0 PPM");
    ppm = 0.0f;
  }
  Serial.print("CO PPM: ");
  Serial.println(ppm);
  return ppm;
}

// =====================================================
// Publikasi Telemetri Sensor ke MQTT
// =====================================================

void publishSensorData() {
  float o2 = readO2();
  float co = readCO();

  if (!mqttClient.connected()) {
    Serial.println("MQTT belum terhubung, melewati publish telemetri.");
    return;
  }

  String timestamp = getTimestamp();

  JsonDocument doc;
  doc["vessel_ship"] = "SIMULATED_VESSEL_01";
  doc["location_work"] = "ENGINE_PUMP_ROOM";
  doc["o2"] = o2;
  doc["co"] = co;
  doc["alarm"] = (int)alarmLevel;

  const char* alarmNames[] = { "NONE", "SAFE", "WARNING", "DANGER" };
  doc["alarm_status"] = alarmNames[alarmLevel];
  doc["timestamp"] = timestamp;

  char payload[512];
  serializeJson(doc, payload, sizeof(payload));

  bool success = mqttClient.publish(MQTT_TOPIC, payload);

  if (success) {
    Serial.println("MQTT Published Telemetri:");
    Serial.println(payload);
  } else {
    Serial.println("MQTT Publish Telemetri Gagal!");
  }
}

// =====================================================
// Button Check (dengan Feed Watchdog)
// =====================================================

void checkResetButton() {
  if (digitalRead(BUTTON_RESET) == LOW) {
    unsigned long pressStart = millis();

    while (digitalRead(BUTTON_RESET) == LOW) {
      esp_task_wdt_reset(); // Feed WDT agar tidak panic reboot saat tombol ditahan
      if (millis() - pressStart >= 1000) {
        Serial.println("Reboot ESP32...");
        digitalWrite(RELAY_GREEN, LOW);
        digitalWrite(RELAY_BUZZER, LOW);
        delay(300);
        ESP.restart();
      }
      delay(20);
    }
  }
}

// =====================================================
// Setup
// =====================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Inisialisasi GPIO
  pinMode(RELAY_BUZZER, OUTPUT);
  pinMode(RELAY_GREEN, OUTPUT);
  pinMode(MQ7_ANALOG, INPUT);
  pinMode(BUTTON_RESET, INPUT_PULLUP);

  // Kondisi awal aman: semua relay MATI
  digitalWrite(RELAY_BUZZER, LOW);
  digitalWrite(RELAY_GREEN, LOW);

  // Inisialisasi Sensor O2 I2C dengan batas percobaan (maksimal 5 kali)
  int i2cAttempts = 0;
  while (!oxygen.begin(Oxygen_IICAddress)) {
    Serial.println("Sensor O2 I2C belum terdeteksi! Mencoba ulang...");
    digitalWrite(RELAY_GREEN, HIGH);
    delay(400);
    digitalWrite(RELAY_GREEN, LOW);
    delay(400);
    i2cAttempts++;
    if (i2cAttempts >= 5) {
      digitalWrite(RELAY_BUZZER, HIGH);
      digitalWrite(RELAY_GREEN, LOW);
      Serial.println("Sensor O2 tidak merespons setelah 5 percobaan. Lanjut ke inisialisasi jaringan.");
      break;
    }
  }
  if (i2cAttempts < 5) {
    Serial.println("Sensor O2 I2C berhasil terhubung!");
  }

  // ---------------------------------------------------
  // Indikator 2: Kalibrasi Sensor MQ7 (CO)
  // Lampu menyala konstan selama proses kalibrasi (~15 detik)
  // ---------------------------------------------------
  Serial.println("Mengkalibrasi Sensor MQ7 (tunggu ~15 detik di udara bersih)...");
  digitalWrite(RELAY_GREEN, HIGH);
  mq7.calibrate();
  digitalWrite(RELAY_GREEN, LOW);
  Serial.print("Kalibrasi MQ7 selesai! Nilai R0 yang diperoleh = ");
  Serial.println(mq7.getR0(), 4);

  // ---------------------------------------------------
  // Indikator 3: Koneksi WiFi (berkedip halus selama proses)
  // ---------------------------------------------------
  connectWiFi();

  // Sinkronisasi Waktu NTP
  configTime(0, 0, NTP_SERVER);

  // Konfigurasi MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(512);
  mqttClient.setSocketTimeout(2);

  connectMQTT();

  // ---------------------------------------------------
  // Indikator 4: Setup Selesai & Sistem Siap
  // Lampu menyala solid 1 detik menandakan inisialisasi tuntas
  // ---------------------------------------------------
  Serial.println("--- Setup Done ---");
  digitalWrite(RELAY_GREEN, HIGH);
  delay(1000);
  digitalWrite(RELAY_GREEN, LOW);

  // ---------------------------------------------------
  // Inisialisasi Watchdog Timer (WDT)
  // Diaktifkan setelah setup selesai agar kalibrasi 15s dan
  // handshake WiFi tidak memicu false reboot
  // ---------------------------------------------------
  initWatchdog();
}

// =====================================================
// Loop
// =====================================================

void loop() {
  // Feed / Reset Watchdog Timer agar ESP32 tahu loop berjalan normal
  esp_task_wdt_reset();

  // Reset button
  checkResetButton();

  // Koneksi WiFi & MQTT
  maintainConnections();

  mqttClient.loop();

  // Update alarm (LED & Buzzer)
  updateAlarm();

  // Kirim telemetri sensor setiap 1 detik
  static unsigned long lastPublish = 0;
  if (millis() - lastPublish >= 1000) {
    lastPublish = millis();
    publishSensorData();
  }
}