import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { WebView } from "react-native-webview";

const DEFAULT_BACKEND_URL = "http://192.168.1.100:8000";

type FaceInfo = {
  name: string;
  score: number;
  bbox: number[];
};

type LatestResponse = {
  metadata: {
    upstream_frame_id?: string;
    esp32_capture_epoch_ms?: number;
    esp32_capture_epoch_iso?: string;
    server_received_epoch_ms?: number;
    server_received_epoch_iso?: string;
    recognition_done_epoch_ms?: number;
    recognition_done_epoch_iso?: string;
    processing_time_ms?: number;
    recognized_names?: string[];
  };
  recognized_faces: FaceInfo[];
};

function normalizeBaseUrl(rawValue: string): string {
  return rawValue.trim().replace(/\/+$/, "");
}

function formatTime(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const hms = d.toLocaleTimeString("vi-VN", { hour12: false });
    const ms = String(d.getMilliseconds()).padStart(3, "0");
    return `${hms}.${ms}`;
  } catch {
    return iso;
  }
}

function getInitials(name: string): string {
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}

function streamHtml(streamUrl: string): string {
  return `
<!doctype html>
<html>
  <head>
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <style>
      html, body { margin: 0; padding: 0; width: 100%; height: 100%; background: #010409; }
      .wrap { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
      img { width: 100%; height: 100%; object-fit: contain; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <img src="${streamUrl}" alt="mjpeg stream" />
    </div>
  </body>
</html>`;
}

// --- Sub-components ---

function LiveDot() {
  const pulse = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.8, duration: 900, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: true }),
      ])
    ).start();
  }, [pulse]);
  return (
    <View style={styles.liveDotWrap}>
      <Animated.View style={[styles.liveDotRing, { transform: [{ scale: pulse }] }]} />
      <View style={styles.liveDot} />
    </View>
  );
}

function FaceChip({ face }: { face: FaceInfo }) {
  const initials = getInitials(face.name);
  const pct = Math.round(face.score * 100);
  return (
    <View style={styles.faceChip}>
      <View style={styles.faceAvatar}>
        <Text style={styles.faceAvatarText}>{initials}</Text>
      </View>
      <Text style={styles.faceName}>{face.name}</Text>
      <Text style={styles.faceScore}>{pct}%</Text>
    </View>
  );
}

function MetaCard({
  label,
  value,
  accent,
  highlight,
  full,
  latencyPct,
}: {
  label: string;
  value: string;
  accent?: boolean;
  highlight?: boolean;
  full?: boolean;
  latencyPct?: number;
}) {
  const barWidth = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (latencyPct !== undefined) {
      Animated.timing(barWidth, {
        toValue: latencyPct,
        duration: 500,
        useNativeDriver: false,
      }).start();
    }
  }, [latencyPct, barWidth]);

  return (
    <View style={[styles.metaCard, full && styles.metaCardFull]}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text
        style={[
          styles.metaValue,
          accent && styles.metaValueAccent,
          highlight && styles.metaValueHighlight,
        ]}
        numberOfLines={2}
      >
        {value}
      </Text>
      {latencyPct !== undefined && (
        <View style={styles.latencyBar}>
          <Animated.View
            style={[
              styles.latencyFill,
              {
                width: barWidth.interpolate({
                  inputRange: [0, 100],
                  outputRange: ["0%", "100%"],
                }),
              },
            ]}
          />
        </View>
      )}
    </View>
  );
}

// --- Main App ---

export default function App() {
  const [backendInput, setBackendInput] = useState(DEFAULT_BACKEND_URL);
  const [backendBaseUrl, setBackendBaseUrl] = useState(DEFAULT_BACKEND_URL);
  const [latest, setLatest] = useState<LatestResponse | null>(null);
  const [mobileReceivedIso, setMobileReceivedIso] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>("");

  const streamUrl = useMemo(() => `${backendBaseUrl}/stream`, [backendBaseUrl]);

  const fetchLatest = useCallback(async () => {
    try {
      const response = await fetch(`${backendBaseUrl}/latest`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as LatestResponse;
      setMobileReceivedIso(new Date().toISOString());
      setLatest(payload);
      setError("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Lỗi không xác định";
      setError(`Không lấy được dữ liệu: ${message}`);
    } finally {
      setIsLoading(false);
    }
  }, [backendBaseUrl]);

  useEffect(() => {
    setIsLoading(true);
    void fetchLatest();
    const timer = setInterval(() => void fetchLatest(), 1200);
    return () => clearInterval(timer);
  }, [fetchLatest]);

  const applyBackendUrl = () => {
    const normalized = normalizeBaseUrl(backendInput);
    if (normalized) setBackendBaseUrl(normalized);
  };

  const faces = latest?.recognized_faces ?? [];
  const latencyMs = latest?.metadata.processing_time_ms ?? 0;
  const latencyPct = Math.min((latencyMs / 500) * 100, 100);

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <View style={styles.headerLeft}>
            <LiveDot />
            <View>
              <Text style={styles.title}>Màn Hình An Ninh</Text>
              <Text style={styles.subtitle}>ESP32-CAM · InsightFace · Thời gian thực</Text>
            </View>
          </View>
          <View style={styles.liveBadge}>
            <Text style={styles.liveBadgeText}>TRỰC TIẾP</Text>
          </View>
        </View>
      </View>

      {/* URL Bar */}
      <View style={styles.urlBar}>
        <TextInput
          style={styles.input}
          value={backendInput}
          onChangeText={setBackendInput}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="http://192.168.x.x:8000"
          placeholderTextColor="#484f58"
          onSubmitEditing={applyBackendUrl}
        />
        <Pressable
          style={({ pressed }) => [styles.applyBtn, pressed && styles.applyBtnPressed]}
          onPress={applyBackendUrl}
        >
          <Text style={styles.applyBtnText}>Áp dụng</Text>
        </Pressable>
      </View>

      {/* Loading strip */}
      {isLoading && (
        <View style={styles.loadingStrip}>
          <ActivityIndicator size="small" color="#388bfd" style={{ marginRight: 6 }} />
          <Text style={styles.loadingText}>Đang kết nối...</Text>
        </View>
      )}

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Stream */}
        <View style={styles.streamCard}>
          <View style={styles.streamBadge}>
            <View style={styles.recDot} />
            <Text style={styles.recText}>REC</Text>
          </View>
          <WebView
            originWhitelist={["*"]}
            source={{ html: streamHtml(streamUrl) }}
            style={styles.webview}
            javaScriptEnabled={false}
            allowsInlineMediaPlayback
          />
        </View>

        {/* Error */}
        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>⚠ {error}</Text>
          </View>
        ) : null}

        {/* Faces */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>KHUÔN MẶT NHẬN DIỆN</Text>
            <Pressable
              style={({ pressed }) => [styles.refreshBtn, pressed && { opacity: 0.6 }]}
              onPress={() => void fetchLatest()}
            >
              <Text style={styles.refreshBtnText}>↻ Làm mới</Text>
            </Pressable>
          </View>
          <View style={styles.facesWrap}>
            {faces.length > 0 ? (
              faces.map((f, i) => <FaceChip key={i} face={f} />)
            ) : (
              <Text style={styles.emptyText}>Chưa phát hiện khuôn mặt nào</Text>
            )}
          </View>
        </View>

        {/* Metadata Grid */}
        <View style={styles.metaGrid}>
          <MetaCard
            label="ESP32 chụp lúc"
            value={formatTime(latest?.metadata.esp32_capture_epoch_iso)}
            accent
          />
          <MetaCard
            label="Server tiếp nhận"
            value={formatTime(latest?.metadata.server_received_epoch_iso)}
          />
          <MetaCard label="Mobile nhận lúc" value={formatTime(mobileReceivedIso)} />
          <MetaCard
            label="Xử lý xong lúc"
            value={formatTime(latest?.metadata.recognition_done_epoch_iso)}
          />
          <MetaCard
            label="Độ trễ xử lý"
            value={`${latencyMs} ms`}
            highlight
            full
            latencyPct={latencyPct}
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const C = {
  bg: "#0d1117",
  surface: "#161b22",
  border: "#21262d",
  borderMid: "#30363d",
  text: "#e6edf3",
  textMuted: "#8b949e",
  textDim: "#7d8590",
  textDimmer: "#484f58",
  green: "#3fb950",
  blue: "#388bfd",
  blueLight: "#79c0ff",
  red: "#f85149",
  mono: "monospace" as const,
};

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: C.bg },

  header: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 12,
    borderBottomWidth: 0.5,
    borderBottomColor: C.border,
  },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  liveDotWrap: { width: 18, height: 18, alignItems: "center", justifyContent: "center" },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: C.green,
    position: "absolute",
  },
  liveDotRing: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: "rgba(63,185,80,0.2)",
    position: "absolute",
  },
  title: { color: C.text, fontSize: 16, fontWeight: "600", letterSpacing: -0.3 },
  subtitle: { color: C.textDim, fontSize: 11, marginTop: 2 },
  liveBadge: {
    backgroundColor: "rgba(63,185,80,0.12)",
    borderWidth: 0.5,
    borderColor: "rgba(63,185,80,0.35)",
    borderRadius: 5,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  liveBadgeText: { color: C.green, fontSize: 10, fontWeight: "700", letterSpacing: 0.8 },

  urlBar: {
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: C.surface,
    borderBottomWidth: 0.5,
    borderBottomColor: C.border,
    alignItems: "center",
  },
  input: {
    flex: 1,
    backgroundColor: C.bg,
    color: C.blueLight,
    borderWidth: 0.5,
    borderColor: C.borderMid,
    borderRadius: 7,
    paddingHorizontal: 11,
    paddingVertical: 9,
    fontSize: 12,
    fontFamily: C.mono,
  },
  applyBtn: {
    backgroundColor: C.surface,
    borderWidth: 0.5,
    borderColor: C.borderMid,
    borderRadius: 7,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  applyBtnPressed: { backgroundColor: C.border },
  applyBtnText: { color: C.textMuted, fontSize: 12, fontWeight: "600" },

  loadingStrip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 7,
    backgroundColor: "rgba(56,139,253,0.08)",
    borderBottomWidth: 0.5,
    borderBottomColor: "rgba(56,139,253,0.2)",
  },
  loadingText: { color: C.blue, fontSize: 12 },

  scroll: { paddingBottom: 32 },

  streamCard: {
    marginHorizontal: 16,
    marginTop: 14,
    borderRadius: 10,
    overflow: "hidden",
    borderWidth: 0.5,
    borderColor: C.border,
    backgroundColor: "#010409",
    aspectRatio: 4 / 3,
  },
  streamBadge: {
    position: "absolute",
    top: 10,
    left: 10,
    zIndex: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    backgroundColor: "rgba(13,17,23,0.85)",
    borderWidth: 0.5,
    borderColor: C.border,
    borderRadius: 5,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  recDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.red },
  recText: { color: C.text, fontSize: 10, fontWeight: "700", letterSpacing: 0.8 },
  webview: { flex: 1, backgroundColor: "#010409" },

  errorBox: {
    marginHorizontal: 16,
    marginTop: 10,
    backgroundColor: "rgba(248,81,73,0.1)",
    borderWidth: 0.5,
    borderColor: "rgba(248,81,73,0.3)",
    borderRadius: 8,
    padding: 12,
  },
  errorText: { color: C.red, fontSize: 12 },

  section: {
    marginHorizontal: 16,
    marginTop: 14,
    backgroundColor: C.surface,
    borderWidth: 0.5,
    borderColor: C.border,
    borderRadius: 10,
    overflow: "hidden",
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: 0.5,
    borderBottomColor: C.border,
  },
  sectionTitle: { color: C.textMuted, fontSize: 10, fontWeight: "600", letterSpacing: 0.8 },
  refreshBtn: {
    borderWidth: 0.5,
    borderColor: C.borderMid,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  refreshBtnText: { color: C.textMuted, fontSize: 11, fontWeight: "500" },
  facesWrap: { flexDirection: "row", flexWrap: "wrap", padding: 10, gap: 6 },
  emptyText: { padding: 14, color: C.textDimmer, fontSize: 12, fontStyle: "italic" },

  faceChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(56,139,253,0.1)",
    borderWidth: 0.5,
    borderColor: "rgba(56,139,253,0.3)",
    borderRadius: 20,
    paddingVertical: 5,
    paddingLeft: 5,
    paddingRight: 10,
  },
  faceAvatar: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "rgba(56,139,253,0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  faceAvatarText: { color: C.blueLight, fontSize: 9, fontWeight: "700" },
  faceName: { color: C.blueLight, fontSize: 12, fontWeight: "600" },
  faceScore: { color: C.blue, fontSize: 10, fontFamily: C.mono },

  metaGrid: {
    marginHorizontal: 16,
    marginTop: 10,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  metaCard: {
    width: "47.5%",
    backgroundColor: C.surface,
    borderWidth: 0.5,
    borderColor: C.border,
    borderRadius: 9,
    padding: 12,
    gap: 4,
  },
  metaCardFull: { width: "100%" },
  metaLabel: {
    color: C.textDim,
    fontSize: 10,
    fontWeight: "600",
    letterSpacing: 0.7,
    textTransform: "uppercase",
  },
  metaValue: { color: C.text, fontSize: 12, fontFamily: C.mono, lineHeight: 18 },
  metaValueAccent: { color: C.blueLight },
  metaValueHighlight: { color: C.green },
  latencyBar: {
    marginTop: 8,
    height: 3,
    backgroundColor: C.border,
    borderRadius: 2,
    overflow: "hidden",
  },
  latencyFill: {
    height: "100%",
    borderRadius: 2,
    backgroundColor: C.green,
  },
});