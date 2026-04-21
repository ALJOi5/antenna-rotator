#include <Arduino.h>
#include <WiFi.h>
#include <LittleFS.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

const char *ssid = "A1-3AAFB1";
const char *password = "zuqohu8423";
const char *apiKey = "FYBCDW-Q3G3B5-JXBJ2R-5P18";
const float baseLat = 46.049358;
const float baseLong = 14.503285;
const int baseAlt = 297;

AsyncWebServer server(80);
AsyncWebSocket ws("/ws");

int currentTrackId = 25544;
bool forceUpdate = true;

void onEvent(AsyncWebSocket *server, AsyncWebSocketClient *client, AwsEventType type,
             void *arg, uint8_t *data, size_t len) {
    if (type == WS_EVT_DATA) {
        data[len] = 0;
        String msg = (char*)data;
        if (msg.startsWith("TRACK:")) {
            currentTrackId = msg.substring(6).toInt();
            forceUpdate = true;
        }
    }
}

void setup() {
    Serial.begin(115200);
    if (!LittleFS.begin()) return;
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) delay(500);

    server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
        request->send(LittleFS, "/index.html", "text/html");
    });
    server.on("/sats.json", HTTP_GET, [](AsyncWebServerRequest *request) {
        request->send(LittleFS, "/sats.json", "application/json");
    });

    ws.onEvent(onEvent);
    server.addHandler(&ws);
    server.begin();
}

void loop() {
    ws.cleanupClients();
    static unsigned long lastRequest = 0;

    if (forceUpdate || (millis() - lastRequest > 60000)) {
        forceUpdate = false;
        lastRequest = millis();

        WiFiClientSecure client;
        client.setInsecure();
        HTTPClient http;

        String url = "https://api.n2yo.com/rest/v1/satellite/positions/" +
                     String(currentTrackId) + "/" + String(baseLat, 6) + "/" + 
                     String(baseLong, 6) + "/" + String(baseAlt) + "/60/&apiKey=" + String(apiKey);

        if (http.begin(client, url)) {
            int httpCode = http.GET();
            if (httpCode == 200) {
                ws.textAll(http.getString());
            }
            http.end();
        }
    }
}