#include <WiFi.h>
#include <HTTPClient.h>
#include <EEPROM.h>
#include <DHT.h>

// ── WiFi credentials ────────────────────────────────────────────────────────
#define WIFI_SSID     "your_hotspot_ssid"
#define WIFI_PASSWORD "your_hotspot_password"

// ── Sensor pins ─────────────────────────────────────────────────────────────
#define DHT_PIN  4    // GPIO4
#define MQ135_PIN 7   // ADC pin

// ── MQ135 constants ──────────────────────────────────────────────────────────
#define RL 10.0f   // Load resistance (kΩ)
#define VC  3.3f   // Supply voltage

// ── Timing ───────────────────────────────────────────────────────────────────
#define SAMPLE_INTERVAL_MS 250
#define SEND_INTERVAL_MS   5000

DHT dht(DHT_PIN, DHT11);
float R0 = 0;

float tempSum = 0, humSum = 0, co2Sum = 0;
int   sampleCount = 0;

unsigned long lastSampleTime = 0;
unsigned long lastSendTime   = 0;

// ── Helpers ──────────────────────────────────────────────────────────────────
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected. Gateway: ");
  Serial.println(WiFi.gatewayIP().toString());
}

void sendData(float avgTemp, float avgHum, float avgCO2) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, skipping send.");
    return;
  }

  String url = "http://" + WiFi.gatewayIP().toString() + "/data";
  String payload = "{\"temperature\":" + String(avgTemp, 2)
                 + ",\"humidity\":"    + String(avgHum,  2)
                 + ",\"co2_ppm\":"     + String(avgCO2,  2) + "}";

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(payload);
  if (code > 0) {
    Serial.printf("POST %s -> HTTP %d\n", url.c_str(), code);
  } else {
    Serial.printf("POST failed: %s\n", http.errorToString(code).c_str());
  }
  http.end();
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  EEPROM.begin(512);
  dht.begin();

  EEPROM.get(0, R0);
  if (isnan(R0) || R0 <= 0) {
    Serial.println("ERROR: No valid R0 in EEPROM. Run calibration first.");
    while (1);
  }
  Serial.printf("Loaded R0: %.4f\n", R0);

  connectWiFi();

  lastSampleTime = millis();
  lastSendTime   = millis();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  // Sample every 250 ms
  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;

    float temp = dht.readTemperature();
    float hum  = dht.readHumidity();

    float Vout = analogRead(MQ135_PIN) * (VC / 4095.0f);
    float co2  = 0;
    if (Vout > 0) {
      float Rs = ((VC / Vout) - 1.0f) * RL;
      co2 = 116.6020682f * powf(Rs / R0, -2.769034857f);
    }

    if (!isnan(temp) && !isnan(hum)) {
      tempSum += temp;
      humSum  += hum;
      co2Sum  += co2;
      sampleCount++;
    }
  }

  // Send average every 5 s
  if (now - lastSendTime >= SEND_INTERVAL_MS && sampleCount > 0) {
    lastSendTime = now;

    float avgTemp = tempSum / sampleCount;
    float avgHum  = humSum  / sampleCount;
    float avgCO2  = co2Sum  / sampleCount;

    Serial.printf("Avg (%d samples) — Temp: %.2f°C | Hum: %.2f%% | CO2: %.2f ppm\n",
                  sampleCount, avgTemp, avgHum, avgCO2);

    sendData(avgTemp, avgHum, avgCO2);

    tempSum = humSum = co2Sum = 0;
    sampleCount = 0;
  }
}
