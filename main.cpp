#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ld2410.h>
#include <FastLED.h> 
#include "Audio.h"

// ================= 配置区 =================
const char* ssid = "20050801";
const char* password = "20050801";

#define RADAR_RX_PIN 16
#define RADAR_TX_PIN 17
#define LED_PIN 5        
#define NUM_LEDS 100      
CRGB leds[NUM_LEDS];

#define I2S_BCLK      26
#define I2S_LRC       25
#define I2S_DOUT      22
// ==========================================

ld2410 radar;
WebServer server(80);
Audio audio; 

String currentLedMode = "off";
unsigned long sunriseStartTime = 0; 

void setup() {
  Serial.begin(115200);
  Serial2.begin(256000, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);

  FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS);
  FastLED.clear(); FastLED.show();
  radar.begin(Serial2);
  
  audio.setPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
  audio.setVolume(5); 
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  
  server.on("/radar", []() {
    String json = "{";
    if (radar.presenceDetected()) {
      json += "\"presence\": true, \"moving_energy\": " + String(radar.movingTargetEnergy()) + ", \"stationary_energy\": " + String(radar.stationaryTargetEnergy());
    } else {
      json += "\"presence\": false, \"moving_energy\": 0, \"stationary_energy\": 0";
    }
    json += "}";
    server.send(200, "application/json", json);
  });

  server.on("/play", []() {
    if (server.hasArg("url")) {
      audio.stopSong(); 
      audio.connecttohost(server.arg("url").c_str()); 
      server.send(200, "text/plain", "Playing");
    }
  });

  server.on("/led", []() {
    if (server.hasArg("mode")) {
      currentLedMode = server.arg("mode");
      if(currentLedMode == "warm_fade_in") {
        sunriseStartTime = millis(); 
      }
      server.send(200, "text/plain", "Mode switched to: " + currentLedMode);
    }
  });

  server.begin();
}

// 🌟 核心：流体光影与渐变引擎
void updateLEDs() {
  if (currentLedMode == "off") {
    fadeToBlackBy(leds, NUM_LEDS, 5);
    FastLED.show();
  } 
  else if (currentLedMode == "breathe_orange") {
    uint8_t b = beatsin8(12, 20, 150); 
    fill_solid(leds, NUM_LEDS, CRGB(b, b/3, 0));
    FastLED.show();
  }
  // 🚨 核心修复：把深海律动蓝光加回来，否则 AI 遇到你翻身时发送指令会失效
  else if (currentLedMode == "breathe_blue") {
    uint8_t b = beatsin8(10, 10, 100); 
    fill_solid(leds, NUM_LEDS, CRGB(0, 0, b));
    FastLED.show();
  }
  else if (currentLedMode == "warm_fade_in") {
    unsigned long elapsed = millis() - sunriseStartTime;
    uint8_t progress = constrain(map(elapsed, 0, 15000, 0, 255), 0, 255); 
    
    CRGB targetColor = CRGB(255, 170, 50); 
    targetColor.nscale8_video(progress);   
    
    fill_solid(leds, NUM_LEDS, targetColor);
    FastLED.show();
  }
  else if (currentLedMode == "solid_white") {
    fill_solid(leds, NUM_LEDS, CRGB(255, 255, 255)); 
    FastLED.show();
  }
}

void loop() {
  radar.read();
  server.handleClient();
  audio.loop(); 
  
  EVERY_N_MILLISECONDS(20) {
    updateLEDs();
  }
}