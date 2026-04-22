#include <Arduino.h>
#include <WiFi.h>
#include <LittleFS.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <TinyGPS++.h>
#include <HardwareSerial.h>

const char *ssid = "A1-3AAFB1";
const char *password = "zuqohu8423";
const char *apiKey = "FYBCDW-Q3G3B5-JXBJ2R-5P18";

float baseLat = 46.049358;
float baseLong = 14.503285;
int baseAlt = 297;
bool gpsLocked = false;

TinyGPSPlus gps;
HardwareSerial GPS_Serial(2);

AsyncWebServer server(80);
AsyncWebSocket ws("/ws");

int currentTrackId = 25544;
bool forceUpdate = true;

void readGPS() {
    while (GPS_Serial.available()) {
        gps.encode(GPS_Serial.read());
    }
    if (gps.location.isValid() && gps.location.isUpdated()) {
        baseLat = gps.location.lat();
        baseLong = gps.location.lng();
        if (gps.altitude.isValid()) baseAlt = (int)gps.altitude.meters();
        if (!gpsLocked) {
            gpsLocked = true;
            forceUpdate = true;
        }
    }
}

void onEvent(AsyncWebSocket *server, AsyncWebSocketClient *client, AwsEventType type,
             void *arg, uint8_t *data, size_t len) {
    if (type == WS_EVT_DATA) {
        String msg = String((char*)data).substring(0, len);
        if (msg.startsWith("TRACK:")) {
            currentTrackId = msg.substring(6).toInt();
            forceUpdate = true;
        }
    }
}

void setup() {
    Serial.begin(115200);
    GPS_Serial.begin(38400, SERIAL_8N1, 25, 26);
    if (!LittleFS.begin()) return;
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        readGPS();
        delay(500);
    }
    server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
        request->send(LittleFS, "/index.html", "text/html");
    });
    server.on("/sats.json", HTTP_GET, [](AsyncWebServerRequest *request) {
        request->send(LittleFS, "/sats.json", "application/json");
    });
    server.on("/gps", HTTP_GET, [](AsyncWebServerRequest *request) {
        StaticJsonDocument<128> doc;
        doc["locked"] = gpsLocked;
        doc["lat"] = baseLat;
        doc["lng"] = baseLong;
        doc["alt"] = baseAlt;
        doc["sats"] = gps.satellites.isValid() ? gps.satellites.value() : 0;
        String out;
        serializeJson(doc, out);
        request->send(200, "application/json", out);
    });
    ws.onEvent(onEvent);
    server.addHandler(&ws);
    server.begin();
}

void loop() {
    readGPS();
    ws.cleanupClients();
    static unsigned long lastRequest = 0;
    if (forceUpdate || (millis() - lastRequest > 60000)) {
        forceUpdate = false;
        lastRequest = millis();
        WiFiClientSecure client;
        client.setInsecure();
        HTTPClient http;
        String url = "https://api.n2yo.com/rest/v1/satellite/positions/" +
                     String(currentTrackId) + "/" +
                     String(baseLat, 6) + "/" +
                     String(baseLong, 6) + "/" +
                     String(baseAlt) + "/60/?apiKey=" + String(apiKey);
        if (http.begin(client, url)) {
            int httpCode = http.GET();
            if (httpCode == 200) ws.textAll(http.getString());
            http.end();
        }
    }
}