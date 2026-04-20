#include <Arduino.h>

#include <config.h>
#include <camera.h>
#include <timesync.h>
#include <transport.h>

timesync::CameraClock g_camera_clock;

void setup() {
	Serial.begin(115200);
	delay(300);
	Serial.println();
	Serial.println("[boot] ESP32-CAM realtime node starting...");

	if (!transport::connectWiFi(WIFI_SSID, WIFI_PASSWORD, CAMERA_HOSTNAME)) {
		Serial.println("[boot] wifi failed, restarting in 3s");
		delay(3000);
		ESP.restart();
	}

	g_camera_clock.begin(CAMERA_TIMEZONE, NTP_SERVER_1, NTP_SERVER_2, NTP_SYNC_TIMEOUT_MS);
	Serial.printf("[clock] ntp synced = %s\n", g_camera_clock.synced() ? "true" : "false");

	if (!cam::begin()) {
		Serial.println("[boot] camera init failed, restarting in 3s");
		delay(3000);
		ESP.restart();
	}

	if (!transport::startServer(&g_camera_clock)) {
		Serial.println("[boot] http server failed, restarting in 3s");
		delay(3000);
		ESP.restart();
	}

	Serial.println("[boot] ready");
}

void loop() {
	delay(1000);
}

