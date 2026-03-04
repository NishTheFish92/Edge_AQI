#include <DHT.h>

// Define the pin where DHT11 is connected
#define DHTPIN 4        // GPIO4 on ESP32
#define DHTTYPE DHT11   // DHT11 sensor type

// Initialize DHT sensor
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  
  // Initialize DHT sensor
  dht.begin();
  
  Serial.println("DHT11 Sensor Test");
  Serial.println("-------------------");
}

void loop() {
  // Wait a few seconds between measurements
  delay(2000);
  
  // Read humidity
  float humidity = dht.readHumidity();
  
  // Read temperature in Celsius
  float temperature = dht.readTemperature();
  
  
  // Check if readings failed
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("Failed to read from DHT sensor!");
    return;
  }
  
  // Calculate heat index in Celsius
  float heatIndexC = dht.computeHeatIndex(temperature, humidity, false);
  
  // Calculate heat index in Fahrenheit
  
  // Display the results
  Serial.println("-------------------");
  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");
  
  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" °C");

  Serial.print("Heat Index: ");
  Serial.print(heatIndexC);
  Serial.println(" °C");
  
  Serial.println("-------------------");
}