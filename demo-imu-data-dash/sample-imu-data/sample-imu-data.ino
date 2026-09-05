/*
 * BLE IMU Streamer
 *
 * Streams six-axis MPU6050 data over BLE as newline-terminated CSV:
 *
 *     ax,ay,az,gx,gy,gz\n
 *
 * Accelerometer in g, gyroscope in deg/s, two decimals each. Pairs with the
 * web dashboard one folder up - serve it and press Connect.
 *
 * Board: ESP32-S3 (onboard RGB LED on GPIO 48).
 * Libraries: MPU6050_light by rfetick. BLE ships with the ESP32 core.
 */

#include <Wire.h>
#include <MPU6050_light.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "env.h"

/* Nordic UART Service. Only the TX (notify) characteristic exists: the node
   streams and the browser listens, nothing is ever written back. */
#define SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define TX_CHAR_UUID "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

#define RGB_BUILTIN_PIN 48
#define FREQUENCY_HZ    100
#define INTERVAL_MS     (1000 / FREQUENCY_HZ)

/* One frame is ~40 bytes. The default ATT MTU of 23 leaves just 20 bytes of
   payload, so every frame would be chopped across two notifications for the
   receiver to reassemble. Asking for a larger MTU keeps one frame in one
   notification. */
#define PREFERRED_MTU 128

// Accelerometer offsets from the calibration script
const float FACTORY_ACC_X = -0.01;
const float FACTORY_ACC_Y = 0.04;
const float FACTORY_ACC_Z = 0.03;

MPU6050 mySensor(Wire);
BLEServer *pServer = nullptr;
BLECharacteristic *pTxCharacteristic = nullptr;

// Written from the BLE callback task, read from loop()
volatile bool deviceConnected = false;
bool oldDeviceConnected = false;

unsigned long last_interval_ms = 0;
unsigned long connectionTime = 0;

void setRGB(uint8_t r, uint8_t g, uint8_t b) {
  neopixelWrite(RGB_BUILTIN_PIN, r, g, b);
}

void blinkRGB(uint8_t r, uint8_t g, uint8_t b, int count, int speed) {
  for (int i = 0; i < count; i++) {
    setRGB(r, g, b);
    delay(speed);
    setRGB(0, 0, 0);
    delay(speed);
  }
}

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) {
    deviceConnected = true;
    connectionTime = millis();

    /* Ask for a 7.5-15 ms connection interval (the values are in units of
       1.25 ms). The previous 0x10-0x20 requested 20-40 ms, which cannot carry
       100 notifications a second, so the stream quietly ran well under
       FREQUENCY_HZ. The central may refuse; the dashboard's rate readout
       shows what actually arrives. */
    server->updateConnParams(server->getConnId(), 0x06, 0x0C, 0, 400);
  }

  void onDisconnect(BLEServer *server) {
    deviceConnected = false;
  }
};

void setup() {
  Serial.begin(115200);
  Wire.begin();

  byte status = mySensor.begin();
  if (status != 0) {
    Serial.printf("MPU6050 init failed (status %d)\n", status);
    /* Keep blinking red rather than spinning in a bare while(1) - that starves
       the task watchdog, so the board reboots and hides the actual fault. */
    while (true) {
      blinkRGB(128, 0, 0, 1, 500);
    }
  }

  Serial.println("Calibrating gyro - keep the board still...");
  blinkRGB(0, 0, 128, 2, 500);
  setRGB(0, 0, 128);

  mySensor.calcOffsets(true, false);  // gyro yes, accel no
  blinkRGB(0, 128, 0, 3, 200);

  // Accel keeps the bench-measured offsets instead of whatever pose it booted in
  mySensor.setAccOffsets(FACTORY_ACC_X, FACTORY_ACC_Y, FACTORY_ACC_Z);
  setRGB(0, 0, 0);

  // ── BLE ──────────────────────────────────────────────────────────────────
  BLEDevice::init(BLE_DEVICE_NAME);
  BLEDevice::setMTU(PREFERRED_MTU);

  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);
  pTxCharacteristic = pService->createCharacteristic(TX_CHAR_UUID,
                                                     BLECharacteristic::PROPERTY_NOTIFY);
  pTxCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  /* Put the service UUID in the advertisement. Without this it is never
     broadcast, so a central can only match on the device name - and Web
     Bluetooth cannot filter on the service at all. A 128-bit UUID plus this
     device name is more than the 31-byte advertisement holds, so the name
     rides in the scan response; the core moves it there by itself while
     scan response is enabled. */
  BLEAdvertising *pAdvertising = pServer->getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMaxPreferred(0x12);
  pAdvertising->start();

  Serial.printf("Advertising as \"%s\", streaming at %d Hz\n",
                BLE_DEVICE_NAME, FREQUENCY_HZ);
}

void loop() {
  // Client went away: let the stack settle, then advertise again
  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    pServer->startAdvertising();
    Serial.println("Client lost - advertising again");
    oldDeviceConnected = false;
  }

  // Client just arrived
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = true;
    Serial.printf("Client connected (MTU %u)\n", BLEDevice::getMTU());
    blinkRGB(0, 128, 0, 3, 200);
  }

  if (deviceConnected) {
    // Give the central 100 ms to finish service discovery before streaming
    if (millis() - connectionTime < 100) return;

    unsigned long now = millis();
    if (now - last_interval_ms < INTERVAL_MS) return;
    last_interval_ms = now;

    mySensor.update();

    /* snprintf into a fixed buffer instead of concatenating Strings. The old
       version built seven temporary Strings per frame, a hundred times a
       second, which fragments the heap over a long session. */
    char frame[64];
    int len = snprintf(frame, sizeof(frame), "%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n",
                       mySensor.getAccX(), mySensor.getAccY(), mySensor.getAccZ(),
                       mySensor.getGyroX(), mySensor.getGyroY(), mySensor.getGyroZ());
    // snprintf returns the length it wanted, so clamp before trusting it
    if (len < 0) return;
    if (len > (int)sizeof(frame) - 1) len = sizeof(frame) - 1;

    pTxCharacteristic->setValue((uint8_t *)frame, len);
    pTxCharacteristic->notify();
  } else {
    // Advertising: blink purple
    static unsigned long lastBlinkChange = 0;
    static bool isPurple = false;
    if (millis() - lastBlinkChange > 500) {
      lastBlinkChange = millis();
      isPurple = !isPurple;
      setRGB(isPurple ? 128 : 0, 0, isPurple ? 128 : 0);
    }
  }
}
