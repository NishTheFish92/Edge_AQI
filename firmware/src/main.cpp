#include <WiFi.h>
#include <HTTPClient.h>
#include <EEPROM.h>
#include <DHT.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <U8g2lib.h>

// ── WiFi credentials (see secrets.h — do not commit) ────────────────────────
#include "secrets.h"

// ── Sensor and led pins ─────────────────────────────────────────────────────────────
#define LED_PIN 48
#define DHT_PIN  4    // GPIO4
#define MQ135_PIN 7   // ADC pin

// ── MQ135 constants ──────────────────────────────────────────────────────────
#define RL 10.0f        // Load resistance (kΩ)
#define VC  3.3f        // Supply voltage
#define R0_DEFAULT 10.0f  // Fallback R0 if EEPROM is blank — replace with your calibrated value

// ── Timing ───────────────────────────────────────────────────────────────────
#define SAMPLE_INTERVAL_MS 250
#define SEND_INTERVAL_MS   5000

DHT dht(DHT_PIN, DHT11);
Adafruit_NeoPixel led(1, LED_PIN, NEO_GRB + NEO_KHZ800);

// 1.3" OLED — SH1106 128×64 over hardware I2C
// If your display uses SSD1306 instead, swap this line with:
//   U8G2_SSD1306_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE);
U8G2_SH1106_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE);

float R0 = 0;

float tempSum = 0, humSum = 0, co2Sum = 0;
int   sampleCount = 0;

unsigned long lastSampleTime = 0;
unsigned long lastSendTime   = 0;

// ── Helpers ──────────────────────────────────────────────────────────────────
void setLED(bool wifiOk) {
  led.setPixelColor(0, wifiOk ? led.Color(0, 255, 0)   // green = connected
                               : led.Color(255, 0, 0)); // red   = disconnected
  led.show();
}

void updateDisplay(float temp, float hum, float co2) {
  char buf[32];
  display.clearBuffer();
  display.setFont(u8g2_font_ncenB08_tr);

  display.drawStr(0, 12, "Air Quality Monitor");
  display.drawHLine(0, 14, 128);

  snprintf(buf, sizeof(buf), "Temp: %.1f C", temp);
  display.drawStr(0, 30, buf);

  snprintf(buf, sizeof(buf), "Hum:  %.1f %%", hum);
  display.drawStr(0, 44, buf);

  snprintf(buf, sizeof(buf), "CO2:  %.0f ppm", co2);
  display.drawStr(0, 58, buf);

  display.sendBuffer();
}

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

  String url = "http://" + WiFi.gatewayIP().toString() + ":5000/sensor";
  String payload = "{\"temperature\":" + String(avgTemp, 2)
                 + ",\"humidity\":"    + String(avgHum,  2)
                 + ",\"co2_ppm\":"     + String(avgCO2,  2) + "}";

  const int MAX_ATTEMPTS = 3;
  for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(8000);

    int code = http.POST(payload);
    if (code > 0) {
      Serial.printf("POST -> HTTP %d (attempt %d)\n", code, attempt);
      http.end();
      return;
    }
    Serial.printf("POST attempt %d/%d failed: %s\n", attempt, MAX_ATTEMPTS,
                  HTTPClient::errorToString(code).c_str());
    http.end();
    if (attempt < MAX_ATTEMPTS) delay(1000);
  }
  Serial.println("All POST attempts failed, dropping reading.");
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  EEPROM.begin(512);
  dht.begin();

  // LED — red until WiFi connects
  led.begin();
  led.setBrightness(50);
  setLED(false);

  // OLED
  display.begin();
  display.clearBuffer();
  display.setFont(u8g2_font_ncenB08_tr);
  display.drawStr(0, 30, "Connecting WiFi...");
  display.sendBuffer();

  EEPROM.get(0, R0);
  if (isnan(R0) || R0 <= 0) {
    Serial.println("WARNING: No valid R0 in EEPROM. Using R0_DEFAULT — run calibration and re-flash for accurate CO2 readings.");
    R0 = R0_DEFAULT;
  }
  Serial.printf("Using R0: %.4f\n", R0);

  connectWiFi();
  setLED(true);  // green — connected

  display.clearBuffer();
  display.setFont(u8g2_font_ncenB08_tr);
  display.drawStr(0, 30, "WiFi Connected!");
  display.sendBuffer();
  delay(1000);

  lastSampleTime = millis();
  lastSendTime   = millis();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost. Reconnecting...");
    setLED(false);
    WiFi.disconnect();
    connectWiFi();
    setLED(true);
  }

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

    updateDisplay(avgTemp, avgHum, avgCO2);
    sendData(avgTemp, avgHum, avgCO2);

    tempSum = humSum = co2Sum = 0;
    sampleCount = 0;
  }
}
