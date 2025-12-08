/*
 * Arduino Fan & LED Controller
 * * Pin Configuration:
 * - Pin 11: IR Receiver
 * - Pin 9:  DHT11 Data
 * - Pin 6:  Fan Motor 
 * - Pin 10: LED/Light
 */

// Libraries for Temperature Sensor and IR Sensor
#include <DHT.h>
#include <IRremote.hpp>

// Pin definitions
#define IR_RECEIVER_PIN 11
#define DHT_PIN 9
#define MOTOR_PIN 6
#define LED_PIN 10
#define DHT_TYPE DHT11

DHT dht(DHT_PIN, DHT_TYPE);

// State
bool fanState = false;
bool ledState = false;

// Sensor intervals
unsigned long lastSensorRead = 0;
const unsigned long SENSOR_INTERVAL = 2000; 

void setup() {
  Serial.begin(9600);
  
  pinMode(MOTOR_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);
  digitalWrite(LED_PIN, LOW);
  
  dht.begin();
  IrReceiver.begin(IR_RECEIVER_PIN, ENABLE_LED_FEEDBACK);
  
  
  delay(1000);
}

void loop() {
  unsigned long currentMillis = millis();
  
  // 1. READ COMMANDS FROM RPI
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim(); // Removes potential extra spaces
    processCommand(command); // Parse data
  }

  // 2. READ IR REMOTE
  if (IrReceiver.decode()) { // Pauses IR from reading more values
    uint32_t irCode = IrReceiver.decodedIRData.decodedRawData;
    
    // Filter noise (0x0) due to shared ground with 6V motor
    if (irCode != 0x0 && IrReceiver.decodedIRData.protocol != 0) {
      if (irCode == 0xE916FF00) {      // Button 0
        setLEDState(true);
      }
      else if (irCode == 0xF30CFF00) { // Button 1
        setLEDState(false);
      }
    }
    IrReceiver.resume(); // Renables IR 
  }
  
  // 3. SEND DATA TO RPI
  if (currentMillis - lastSensorRead >= SENSOR_INTERVAL) {
    lastSensorRead = currentMillis;
    
    float h = dht.readHumidity();
    float t = dht.readTemperature(); // Celsius
    
    // Error handling
    if (isnan(h) || isnan(t)) { // If the readings from sensor are not numbers
      // Error JSON response
      Serial.println("{\"error\":\"sensor_fail\"}");
    } else {
      // Valid JSON response
      sendJSON(t, h);
    }
  }
}

void processCommand(String command) { // Parses the data from RPI
  if (command.startsWith("FAN:")) {
    int state = command.substring(4).toInt();
    setFanState(state == 1);
  }
  else if (command.startsWith("LED:")) {
    int state = command.substring(4).toInt();
    setLEDState(state == 1);
  }
}

void setFanState(bool state) { // Toggles fan state
    fanState = state; // Set global value
    if (state == true) {
        digitalWrite(MOTOR_PIN, HIGH);
    } else {
        digitalWrite(MOTOR_PIN, LOW);
    }
}

void setLEDState(bool state) { // Toggles fan state
    ledState = state; // Set global value
    if (state == true) {
        digitalWrite(LED_PIN, HIGH);
    } else {
        digitalWrite(LED_PIN, LOW);
    }
}

// Format: {"temp":24.5,"humidity":60.2,"fan":true,"led":false}
void sendJSON(float t, float h) {
    Serial.print("{\"temp\":");
    Serial.print(t, 1);
    Serial.print(",\"humidity\":");
    Serial.print(h, 1);
    Serial.print(",\"fan\":");
    
    if (fanState == true) {
        Serial.print("true");
    } else {
        Serial.print("false");
    }
    
    Serial.print(",\"led\":");
    
    if (ledState == true) {
        Serial.print("true");
    } else {
        Serial.print("false");
    }
    
    Serial.println("}");
}