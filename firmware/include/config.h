#pragma once
#include <string>

#define WIFI_SSID "XYZ"
#define WIFI_PASSWORD "hoianhHung"

// Optional network identity.
#define CAMERA_HOSTNAME "esp32cam-node-01"

// Clock and timezone settings.
#define CAMERA_TIMEZONE "UTC0"
#define NTP_SERVER_1 "pool.ntp.org"
#define NTP_SERVER_2 "time.google.com"
#define NTP_SYNC_TIMEOUT_MS 10000

// Camera tuning for low-latency streaming.
#define CAMERA_JPEG_QUALITY 12
#define CAMERA_XCLK_HZ 20000000

// PSRAM boards can handle higher frame sizes.
#define CAMERA_FRAME_SIZE_WITH_PSRAM FRAMESIZE_VGA
#define CAMERA_FRAME_SIZE_NO_PSRAM FRAMESIZE_QVGA

