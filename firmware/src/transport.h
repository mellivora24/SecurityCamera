#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <esp_http_server.h>
#include <esp_timer.h>

#include <camera.h>
#include <timesync.h>

namespace transport {

struct AppContext {
	timesync::CameraClock *clock;
	volatile uint64_t frame_counter;
};

static AppContext g_ctx{};
static httpd_handle_t g_http_server = nullptr;

static esp_err_t healthHandler(httpd_req_t *req) {
	char payload[256];
	const int written = snprintf(
			payload,
			sizeof(payload),
			"{\"status\":\"ok\",\"uptime_ms\":%llu,\"wifi_rssi\":%d,\"ip\":\"%s\",\"clock_synced\":%s}",
			static_cast<unsigned long long>(g_ctx.clock->uptimeMs()),
			WiFi.RSSI(),
			WiFi.localIP().toString().c_str(),
			g_ctx.clock->synced() ? "true" : "false");

	httpd_resp_set_type(req, "application/json");
	httpd_resp_set_hdr(req, "Cache-Control", "no-store");
	return httpd_resp_send(req, payload, written);
}

static esp_err_t timeHandler(httpd_req_t *req) {
	char payload[220];
	const uint64_t mono_us = static_cast<uint64_t>(esp_timer_get_time());
	const int written = snprintf(
			payload,
			sizeof(payload),
			"{\"camera_epoch_ms\":%llu,\"camera_monotonic_us\":%llu,\"clock_synced\":%s}",
			static_cast<unsigned long long>(g_ctx.clock->epochMs()),
			static_cast<unsigned long long>(mono_us),
			g_ctx.clock->synced() ? "true" : "false");

	httpd_resp_set_type(req, "application/json");
	httpd_resp_set_hdr(req, "Cache-Control", "no-store");
	return httpd_resp_send(req, payload, written);
}

static esp_err_t frameJpegHandler(httpd_req_t *req) {
	camera_fb_t *fb = cam::capture();
	if (fb == nullptr) {
		return httpd_resp_send_500(req);
	}

	const uint64_t frame_id = ++g_ctx.frame_counter;
	const timesync::CaptureTimestamp ts = g_ctx.clock->stamp(frame_id);

	httpd_resp_set_type(req, "image/jpeg");
	httpd_resp_set_hdr(req, "Cache-Control", "no-store");
	httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

	char frame_id_header[32];
	char epoch_header[32];
	char mono_header[32];
	snprintf(frame_id_header, sizeof(frame_id_header), "%llu", static_cast<unsigned long long>(ts.frame_id));
	snprintf(epoch_header, sizeof(epoch_header), "%llu", static_cast<unsigned long long>(ts.capture_epoch_ms));
	snprintf(mono_header, sizeof(mono_header), "%llu", static_cast<unsigned long long>(ts.capture_monotonic_us));

	httpd_resp_set_hdr(req, "X-Frame-Id", frame_id_header);
	httpd_resp_set_hdr(req, "X-Cam-Capture-Epoch-Ms", epoch_header);
	httpd_resp_set_hdr(req, "X-Cam-Capture-Monotonic-Us", mono_header);
	httpd_resp_set_hdr(req, "X-Cam-Clock-Synced", ts.ntp_synced ? "1" : "0");

	const esp_err_t res = httpd_resp_send(req, reinterpret_cast<const char *>(fb->buf), fb->len);
	cam::release(fb);
	return res;
}

static esp_err_t frameMetaHandler(httpd_req_t *req) {
	const uint64_t frame_id = g_ctx.frame_counter;
	const uint64_t mono_us = static_cast<uint64_t>(esp_timer_get_time());
	const uint64_t epoch_ms = g_ctx.clock->epochMs();

	char payload[260];
	const int written = snprintf(
			payload,
			sizeof(payload),
			"{\"last_frame_id\":%llu,\"camera_epoch_ms\":%llu,\"camera_monotonic_us\":%llu,\"clock_synced\":%s}",
			static_cast<unsigned long long>(frame_id),
			static_cast<unsigned long long>(epoch_ms),
			static_cast<unsigned long long>(mono_us),
			g_ctx.clock->synced() ? "true" : "false");

	httpd_resp_set_type(req, "application/json");
	httpd_resp_set_hdr(req, "Cache-Control", "no-store");
	httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
	return httpd_resp_send(req, payload, written);
}

static esp_err_t streamHandler(httpd_req_t *req) {
	static const char *kContentType = "multipart/x-mixed-replace; boundary=frame";
	static const char *kBoundary = "\r\n--frame\r\n";

	httpd_resp_set_type(req, kContentType);
	httpd_resp_set_hdr(req, "Cache-Control", "no-store");
	httpd_resp_set_hdr(req, "Connection", "keep-alive");
	httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
	httpd_resp_set_hdr(req, "X-Accel-Buffering", "no");

	while (true) {
		camera_fb_t *fb = cam::capture();
		if (fb == nullptr) {
			return ESP_FAIL;
		}

		const uint64_t frame_id = ++g_ctx.frame_counter;
		const timesync::CaptureTimestamp ts = g_ctx.clock->stamp(frame_id);

		char part_header[360];
		const int hlen = snprintf(
				part_header,
				sizeof(part_header),
				"Content-Type: image/jpeg\r\n"
				"Content-Length: %u\r\n"
				"X-Frame-Id: %llu\r\n"
				"X-Cam-Capture-Epoch-Ms: %llu\r\n"
				"X-Cam-Capture-Monotonic-Us: %llu\r\n"
				"X-Cam-Clock-Synced: %u\r\n\r\n",
				static_cast<unsigned>(fb->len),
				static_cast<unsigned long long>(ts.frame_id),
				static_cast<unsigned long long>(ts.capture_epoch_ms),
				static_cast<unsigned long long>(ts.capture_monotonic_us),
				static_cast<unsigned>(ts.ntp_synced ? 1 : 0));

		esp_err_t err = httpd_resp_send_chunk(req, kBoundary, strlen(kBoundary));
		if (err == ESP_OK) {
			err = httpd_resp_send_chunk(req, part_header, hlen);
		}
		if (err == ESP_OK) {
			err = httpd_resp_send_chunk(req, reinterpret_cast<const char *>(fb->buf), fb->len);
		}
		if (err == ESP_OK) {
			err = httpd_resp_send_chunk(req, "\r\n", 2);
		}

		cam::release(fb);

		if (err != ESP_OK) {
			break;
		}

		delay(1);
	}

	return ESP_OK;
}

inline bool connectWiFi(const char *ssid, const char *password, const char *hostname) {
	WiFi.mode(WIFI_STA);
	WiFi.setHostname(hostname);
	WiFi.begin(ssid, password);

	Serial.printf("[wifi] connecting to %s", ssid);
	uint32_t wait_ms = 0;
	while (WiFi.status() != WL_CONNECTED && wait_ms < 30000) {
		delay(250);
		wait_ms += 250;
		Serial.print('.');
	}
	Serial.println();

	if (WiFi.status() != WL_CONNECTED) {
		Serial.println("[wifi] connection timeout");
		return false;
	}

	Serial.printf("[wifi] connected, ip=%s\n", WiFi.localIP().toString().c_str());
	return true;
}

inline bool startServer(timesync::CameraClock *clock) {
	g_ctx.clock = clock;
	g_ctx.frame_counter = 0;

	httpd_config_t config = HTTPD_DEFAULT_CONFIG();
	config.server_port = 80;
	config.ctrl_port = 32768;
	config.stack_size = 8192;
	config.max_uri_handlers = 12;

	const esp_err_t start_err = httpd_start(&g_http_server, &config);
	if (start_err != ESP_OK) {
		Serial.printf("[http] start failed: 0x%x\n", start_err);
		return false;
	}

	httpd_uri_t health_uri = {.uri = "/health", .method = HTTP_GET, .handler = healthHandler, .user_ctx = nullptr};
	httpd_uri_t time_uri = {.uri = "/time", .method = HTTP_GET, .handler = timeHandler, .user_ctx = nullptr};
	httpd_uri_t frame_uri = {.uri = "/frame.jpg", .method = HTTP_GET, .handler = frameJpegHandler, .user_ctx = nullptr};
	httpd_uri_t frame_meta_uri = {.uri = "/frame/meta", .method = HTTP_GET, .handler = frameMetaHandler, .user_ctx = nullptr};
	httpd_uri_t stream_uri = {.uri = "/stream", .method = HTTP_GET, .handler = streamHandler, .user_ctx = nullptr};

	httpd_register_uri_handler(g_http_server, &health_uri);
	httpd_register_uri_handler(g_http_server, &time_uri);
	httpd_register_uri_handler(g_http_server, &frame_uri);
	httpd_register_uri_handler(g_http_server, &frame_meta_uri);
	httpd_register_uri_handler(g_http_server, &stream_uri);

	Serial.println("[http] endpoints: /stream, /frame.jpg, /frame/meta, /time, /health");
	return true;
}

}  // namespace transport
