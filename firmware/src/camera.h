#pragma once

#include <Arduino.h>
#include <esp_camera.h>
#include <config.h>

namespace cam {

// AI Thinker ESP32-CAM pin map.
constexpr int PWDN_GPIO_NUM = 32;
constexpr int RESET_GPIO_NUM = -1;
constexpr int XCLK_GPIO_NUM = 0;
constexpr int SIOD_GPIO_NUM = 26;
constexpr int SIOC_GPIO_NUM = 27;

constexpr int Y9_GPIO_NUM = 35;
constexpr int Y8_GPIO_NUM = 34;
constexpr int Y7_GPIO_NUM = 39;
constexpr int Y6_GPIO_NUM = 36;
constexpr int Y5_GPIO_NUM = 21;
constexpr int Y4_GPIO_NUM = 19;
constexpr int Y3_GPIO_NUM = 18;
constexpr int Y2_GPIO_NUM = 5;
constexpr int VSYNC_GPIO_NUM = 25;
constexpr int HREF_GPIO_NUM = 23;
constexpr int PCLK_GPIO_NUM = 22;

inline bool begin() {
	camera_config_t config{};
	config.ledc_channel = LEDC_CHANNEL_0;
	config.ledc_timer = LEDC_TIMER_0;
	config.pin_d0 = Y2_GPIO_NUM;
	config.pin_d1 = Y3_GPIO_NUM;
	config.pin_d2 = Y4_GPIO_NUM;
	config.pin_d3 = Y5_GPIO_NUM;
	config.pin_d4 = Y6_GPIO_NUM;
	config.pin_d5 = Y7_GPIO_NUM;
	config.pin_d6 = Y8_GPIO_NUM;
	config.pin_d7 = Y9_GPIO_NUM;
	config.pin_xclk = XCLK_GPIO_NUM;
	config.pin_pclk = PCLK_GPIO_NUM;
	config.pin_vsync = VSYNC_GPIO_NUM;
	config.pin_href = HREF_GPIO_NUM;
	config.pin_sccb_sda = SIOD_GPIO_NUM;
	config.pin_sccb_scl = SIOC_GPIO_NUM;
	config.pin_pwdn = PWDN_GPIO_NUM;
	config.pin_reset = RESET_GPIO_NUM;
	config.xclk_freq_hz = CAMERA_XCLK_HZ;
	config.frame_size = psramFound() ? CAMERA_FRAME_SIZE_WITH_PSRAM : CAMERA_FRAME_SIZE_NO_PSRAM;
	config.pixel_format = PIXFORMAT_JPEG;
	config.grab_mode = CAMERA_GRAB_LATEST;
	config.fb_location = CAMERA_FB_IN_PSRAM;
	config.jpeg_quality = CAMERA_JPEG_QUALITY;
	config.fb_count = psramFound() ? 2 : 1;

	const esp_err_t err = esp_camera_init(&config);
	if (err != ESP_OK) {
		Serial.printf("[camera] init failed: 0x%x\n", err);
		return false;
	}

	sensor_t *sensor = esp_camera_sensor_get();
	if (sensor != nullptr) {
		sensor->set_vflip(sensor, 1);
		sensor->set_brightness(sensor, 1);
		sensor->set_saturation(sensor, 0);
	}

	return true;
}

inline camera_fb_t *capture() {
	return esp_camera_fb_get();
}

inline void release(camera_fb_t *fb) {
	if (fb != nullptr) {
		esp_camera_fb_return(fb);
	}
}

}  // namespace cam
