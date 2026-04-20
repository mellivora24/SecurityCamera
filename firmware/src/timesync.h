#pragma once

#include <Arduino.h>
#include <esp_timer.h>
#include <time.h>
#include <sys/time.h>

namespace timesync {

struct CaptureTimestamp {
	uint64_t frame_id;
	uint64_t capture_monotonic_us;
	uint64_t capture_epoch_ms;
	bool ntp_synced;
};

class CameraClock {
 public:
	void begin(const char *tz, const char *ntp1, const char *ntp2, uint32_t sync_timeout_ms) {
		boot_ms_ = millis();
		setenv("TZ", tz, 1);
		tzset();

		configTzTime(tz, ntp1, ntp2);
		synced_ = waitForTimeSync(sync_timeout_ms);
	}

	bool synced() const {
		return synced_;
	}

	uint64_t uptimeMs() const {
		return millis() - boot_ms_;
	}

	CaptureTimestamp stamp(uint64_t frame_id) const {
		CaptureTimestamp ts{};
		ts.frame_id = frame_id;
		ts.capture_monotonic_us = static_cast<uint64_t>(esp_timer_get_time());
		ts.capture_epoch_ms = epochMs();
		ts.ntp_synced = synced_;
		return ts;
	}

	uint64_t epochMs() const {
		struct timeval tv {};
		gettimeofday(&tv, nullptr);
		if (tv.tv_sec <= 0) {
			return 0;
		}
		return static_cast<uint64_t>(tv.tv_sec) * 1000ULL + static_cast<uint64_t>(tv.tv_usec / 1000ULL);
	}

 private:
	static bool waitForTimeSync(uint32_t timeout_ms) {
		const uint32_t start = millis();
		struct tm time_info {};
		while ((millis() - start) < timeout_ms) {
			if (getLocalTime(&time_info, 200)) {
				return true;
			}
			delay(100);
		}
		return false;
	}

	uint32_t boot_ms_ = 0;
	bool synced_ = false;
};

}  // namespace timesync
