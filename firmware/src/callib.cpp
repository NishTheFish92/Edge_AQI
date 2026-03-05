// #include <EEPROM.h>

// const int MQ135_PIN = 7;  // ADC pin
// const float RL = 10.0;      // Load resistance in kΩ (check your module!)
// const float Vc = 3.3;       // ESP32 voltage

// void setup() {
//   Serial.begin(115200);
//   EEPROM.begin(512);
  
//   delay(2500);
//   Serial.println("MQ135 Calibration");
//   Serial.println("Place sensor in CLEAN AIR for 24-48 hours first!");
//   Serial.println("Press any key.");
  
//   while(!Serial.available());
  
//   Take multiple readings
//   float sum = 0;
//   int samples = 150;
  

//   for(int i = 0; i < samples; i++) {
//     float Vout = analogRead(MQ135_PIN) * (Vc / 4095.0);  // 12-bit ADC
//     float Rs = ((Vc / Vout) - 1) * RL;
//     sum += Rs;
//     delay(100);
//   }
  
//   float avgRs = sum / samples;
//   float R0 = avgRs / 3.6;  // For 400ppm CO2
  
//   Serial.print("Average Rs: "); Serial.println(avgRs);
//   Serial.print("Calculated R0: "); Serial.println(R0);
  
//   Save to EEPROM
//   EEPROM.put(0, R0);
//   EEPROM.commit();
  
//   Serial.println("R0 saved to EEPROM!");
//   Serial.println("Calibration complete. Upload your main code now.");
// }

// void loop() {
// }