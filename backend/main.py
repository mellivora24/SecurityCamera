import asyncio
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import cv2
import numpy as np
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from insightface.app import FaceAnalysis


def now_ms() -> int:
	return int(time.time() * 1000)


def ms_to_iso8601(value_ms: int) -> Optional[str]:
	if not value_ms:
		return None
	return datetime.fromtimestamp(value_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_vector(vector: np.ndarray) -> np.ndarray:
	norm = float(np.linalg.norm(vector))
	if norm <= 0.0:
		return vector
	return vector / norm


def parse_int_list(value: str, default: List[int]) -> List[int]:
	try:
		parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
		return parsed if parsed else default
	except ValueError:
		return default


def to_image_bytes(frame_bgr: np.ndarray, quality: int = 90) -> bytes:
	success, buffer = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
	if not success:
		raise RuntimeError("failed to encode jpeg")
	return buffer.tobytes()


def read_exact(raw_stream: Any, length: int) -> bytes:
	chunks: List[bytes] = []
	remaining = length
	while remaining > 0:
		chunk = raw_stream.read(remaining)
		if not chunk:
			raise EOFError("unexpected end of mjpeg stream")
		chunks.append(chunk)
		remaining -= len(chunk)
	return b"".join(chunks)


def extract_boundary(content_type: str) -> bytes:
	match = re.search(r'boundary=(?:"?)([^";]+)', content_type, re.IGNORECASE)
	boundary = match.group(1) if match else "frame"
	return boundary.encode("utf-8")


def iterate_mjpeg_parts(response: requests.Response) -> Iterable[Dict[str, Any]]:
	raw_stream = response.raw
	raw_stream.decode_content = True
	boundary = b"--" + extract_boundary(response.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"))

	while True:
		line = raw_stream.readline()
		if not line:
			return
		if boundary not in line:
			continue

		headers: Dict[str, str] = {}
		while True:
			line = raw_stream.readline()
			if not line:
				return
			if line in (b"\r\n", b"\n"):
				break
			if b":" in line:
				key, value = line.decode("latin-1").split(":", 1)
				headers[key.strip().lower()] = value.strip()

		content_length = int(headers.get("content-length", "0"))
		if content_length <= 0:
			continue

		payload = read_exact(raw_stream, content_length)
		tail = raw_stream.readline()
		if tail and tail not in (b"\r\n", b"\n") and boundary not in tail:
			pass

		yield {"headers": headers, "jpeg": payload}


@dataclass
class RecognitionItem:
	name: str
	score: float
	bbox: List[int]


@dataclass
class FrameSnapshot:
	version: int
	jpeg: bytes
	metadata: Dict[str, Any]
	recognition: List[RecognitionItem] = field(default_factory=list)


class FaceDatabase:
	def __init__(self, face_app: FaceAnalysis, root_dir: Path, threshold: float) -> None:
		self.face_app = face_app
		self.root_dir = root_dir
		self.threshold = threshold
		self.entries: List[Dict[str, Any]] = []

	def load(self) -> None:
		self.entries = []
		self.root_dir.mkdir(parents=True, exist_ok=True)

		for person_dir in sorted(path for path in self.root_dir.iterdir() if path.is_dir()):
			embeddings: List[np.ndarray] = []
			for image_path in sorted(person_dir.rglob("*")):
				if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
					continue
				image = cv2.imread(str(image_path))
				if image is None:
					continue
				faces = self.face_app.get(image)
				if not faces:
					continue
				face = max(faces, key=lambda item: float((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])))
				embedding = self._extract_embedding(face)
				if embedding is not None:
					embeddings.append(embedding)

			if embeddings:
				centroid = normalize_vector(np.mean(np.vstack(embeddings), axis=0))
				self.entries.append({"name": person_dir.name, "embedding": centroid})

	def recognize(self, image_bgr: np.ndarray) -> List[RecognitionItem]:
		if not self.entries:
			return []

		faces = self.face_app.get(image_bgr)
		results: List[RecognitionItem] = []

		for face in faces:
			embedding = self._extract_embedding(face)
			if embedding is None:
				continue

			best_name = "unknown"
			best_score = -1.0
			for entry in self.entries:
				score = float(np.dot(embedding, entry["embedding"]))
				if score > best_score:
					best_score = score
					best_name = str(entry["name"])

			if best_score < self.threshold:
				best_name = "unknown"

			bbox = [int(round(value)) for value in face.bbox.tolist()]
			results.append(RecognitionItem(name=best_name, score=best_score, bbox=bbox))

		return results

	@staticmethod
	def _extract_embedding(face: Any) -> Optional[np.ndarray]:
		embedding = getattr(face, "normed_embedding", None)
		if embedding is None:
			embedding = getattr(face, "embedding", None)
		if embedding is None:
			return None
		return normalize_vector(np.asarray(embedding, dtype=np.float32))


class LatestFrameStore:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._condition = threading.Condition(self._lock)
		self._snapshot: Optional[FrameSnapshot] = None
		self._version = 0

	def publish(self, jpeg: bytes, metadata: Dict[str, Any], recognition: List[RecognitionItem]) -> FrameSnapshot:
		with self._condition:
			self._version += 1
			snapshot = FrameSnapshot(version=self._version, jpeg=jpeg, metadata=metadata, recognition=recognition)
			self._snapshot = snapshot
			self._condition.notify_all()
			return snapshot

	def latest(self) -> Optional[FrameSnapshot]:
		with self._lock:
			return self._snapshot

	def wait_for_update(self, last_version: int, timeout: float = 1.0) -> Optional[FrameSnapshot]:
		with self._condition:
			if self._snapshot is not None and self._snapshot.version != last_version:
				return self._snapshot
			self._condition.wait(timeout=timeout)
			return self._snapshot


class CameraWorker:
	def __init__(self, esp32_url: str, face_db: FaceDatabase, store: LatestFrameStore, jpeg_quality: int = 90) -> None:
		self.esp32_url = esp32_url
		self.face_db = face_db
		self.store = store
		self.jpeg_quality = jpeg_quality
		self._stop_event = threading.Event()
		self._thread: Optional[threading.Thread] = None

	def start(self) -> None:
		if self._thread is not None and self._thread.is_alive():
			return
		self._thread = threading.Thread(target=self._run, name="esp32cam-worker", daemon=True)
		self._thread.start()

	def stop(self) -> None:
		self._stop_event.set()
		if self._thread is not None:
			self._thread.join(timeout=2.0)

	def _run(self) -> None:
		while not self._stop_event.is_set():
			try:
				with requests.get(self.esp32_url, stream=True, timeout=(10, 30)) as response:
					response.raise_for_status()
					for part in iterate_mjpeg_parts(response):
						if self._stop_event.is_set():
							return

						jpeg_bytes = part["jpeg"]
						headers = part["headers"]
						server_received_epoch_ms = now_ms()
						frame_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
						image_bgr = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
						if image_bgr is None:
							continue

						recognition = self.face_db.recognize(image_bgr)
						annotated = self._annotate(image_bgr, recognition, headers, server_received_epoch_ms)
						output_jpeg = to_image_bytes(annotated, quality=self.jpeg_quality)
						recognition_done_epoch_ms = now_ms()

						metadata: Dict[str, Any] = {
							"upstream_frame_id": headers.get("x-frame-id"),
							"esp32_capture_epoch_ms": int(headers.get("x-cam-capture-epoch-ms", "0") or 0),
							"esp32_capture_epoch_iso": ms_to_iso8601(int(headers.get("x-cam-capture-epoch-ms", "0") or 0)),
							"esp32_capture_monotonic_us": int(headers.get("x-cam-capture-monotonic-us", "0") or 0),
							"esp32_clock_synced": headers.get("x-cam-clock-synced", "0") in {"1", "true", "True"},
							"server_received_epoch_ms": server_received_epoch_ms,
							"server_received_epoch_iso": ms_to_iso8601(server_received_epoch_ms),
							"recognition_done_epoch_ms": recognition_done_epoch_ms,
							"recognition_done_epoch_iso": ms_to_iso8601(recognition_done_epoch_ms),
							"processing_time_ms": recognition_done_epoch_ms - server_received_epoch_ms,
							"recognized_names": [item.name for item in recognition],
							"recognized_faces": [
								{"name": item.name, "score": round(item.score, 4), "bbox": item.bbox}
								for item in recognition
							],
						}
						self.store.publish(output_jpeg, metadata, recognition)
			except Exception as exc:
				print(f"[worker] reconnecting after error: {exc}")
				time.sleep(2.0)

	def _annotate(
		self,
		image_bgr: np.ndarray,
		recognition: List[RecognitionItem],
		headers: Dict[str, str],
		server_received_epoch_ms: int,
	) -> np.ndarray:
		annotated = image_bgr.copy()
		overlay_lines = []

		capture_epoch_ms = int(headers.get("x-cam-capture-epoch-ms", "0") or 0)
		overlay_lines.append(f"ESP32: {ms_to_iso8601(capture_epoch_ms) or 'unsynced'}")
		overlay_lines.append(f"Server recv: {ms_to_iso8601(server_received_epoch_ms)}")

		for item in recognition:
			x1, y1, x2, y2 = item.bbox
			cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 2)
			label = f"{item.name} {item.score:.2f}"
			label_y = max(y1 - 8, 18)
			cv2.putText(annotated, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2, cv2.LINE_AA)

		if recognition:
			overlay_lines.append("Faces: " + ", ".join(item.name for item in recognition))
		else:
			overlay_lines.append("Faces: none")

		self._draw_overlay(annotated, overlay_lines)
		return annotated

	@staticmethod
	def _draw_overlay(image_bgr: np.ndarray, lines: List[str]) -> None:
		padding = 10
		line_height = 22
		width = 0
		for line in lines:
			(text_width, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
			width = max(width, text_width)
		height = padding * 2 + line_height * len(lines)
		cv2.rectangle(image_bgr, (0, 0), (width + padding * 2, height), (0, 0, 0), -1)
		for index, line in enumerate(lines):
			y = padding + 16 + index * line_height
			cv2.putText(image_bgr, line, (padding, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def build_app() -> FastAPI:
	esp32_url = os.getenv("ESP32CAM_URL", "http://192.168.137.239/stream")
	face_dir = Path(os.getenv("FACE_DB_DIR", "faces"))
	face_threshold = float(os.getenv("FACE_SIMILARITY_THRESHOLD", "0.45"))
	stream_jpeg_quality = int(os.getenv("STREAM_JPEG_QUALITY", "90"))
	det_size = tuple(parse_int_list(os.getenv("INSIGHTFACE_DET_SIZE", "640,640"), [640, 640]))
	ctx_id = int(os.getenv("INSIGHTFACE_CTX_ID", "-1"))
	providers = [provider.strip() for provider in os.getenv("INSIGHTFACE_PROVIDERS", "CPUExecutionProvider").split(",") if provider.strip()]

	face_app = FaceAnalysis(name=os.getenv("INSIGHTFACE_MODEL_NAME", "buffalo_l"), providers=providers)
	face_app.prepare(ctx_id=ctx_id, det_size=(int(det_size[0]), int(det_size[1])))

	face_db = FaceDatabase(face_app, face_dir, face_threshold)
	face_db.load()

	store = LatestFrameStore()
	worker = CameraWorker(esp32_url, face_db, store, jpeg_quality=stream_jpeg_quality)

	app = FastAPI(title="ESP32CAM Face Relay", version="1.0.0")
	app.add_middleware(
		CORSMiddleware,
		allow_origins=["*"],
		allow_credentials=False,
		allow_methods=["*"],
		allow_headers=["*"],
	)

	app.state.face_db = face_db
	app.state.store = store
	app.state.worker = worker
	app.state.esp32_url = esp32_url

	@app.on_event("startup")
	def _startup() -> None:
		worker.start()

	@app.on_event("shutdown")
	def _shutdown() -> None:
		worker.stop()

	@app.get("/health")
	def health() -> Dict[str, Any]:
		latest = store.latest()
		return {
			"status": "ok",
			"esp32_url": esp32_url,
			"faces_loaded": len(face_db.entries),
			"has_frame": latest is not None,
			"latest": latest.metadata if latest else None,
		}

	@app.get("/latest")
	def latest() -> Dict[str, Any]:
		snapshot = store.latest()
		if snapshot is None:
			raise HTTPException(status_code=404, detail="no frame available yet")
		return {
			"metadata": snapshot.metadata,
			"recognized_faces": [
				{"name": item.name, "score": round(item.score, 4), "bbox": item.bbox}
				for item in snapshot.recognition
			],
		}

	@app.get("/snapshot.jpg")
	def snapshot_jpg() -> Response:
		snapshot = store.latest()
		if snapshot is None:
			raise HTTPException(status_code=404, detail="no frame available yet")
		return Response(content=snapshot.jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

	@app.get("/stream")
	async def stream() -> StreamingResponse:
		boundary = b"--frame\r\n"

		async def generator() -> Iterable[bytes]:
			last_version = -1
			while True:
				snapshot = await asyncio.to_thread(store.wait_for_update, last_version, 1.0)
				if snapshot is None:
					await asyncio.sleep(0.05)
					continue
				last_version = snapshot.version

				metadata = snapshot.metadata
				names = ";".join(item.name for item in snapshot.recognition)
				part_headers = [
					b"Content-Type: image/jpeg",
					f"Content-Length: {len(snapshot.jpeg)}".encode("utf-8"),
					f"X-Recognized-Names: {names}".encode("utf-8"),
					f"X-Server-Received-Epoch-Ms: {metadata.get('server_received_epoch_ms', 0)}".encode("utf-8"),
					f"X-Recognition-Done-Epoch-Ms: {metadata.get('recognition_done_epoch_ms', 0)}".encode("utf-8"),
					f"X-Processing-Time-Ms: {metadata.get('processing_time_ms', 0)}".encode("utf-8"),
					f"X-Cam-Capture-Epoch-Ms: {metadata.get('esp32_capture_epoch_ms', 0)}".encode("utf-8"),
					b"\r\n",
				]
				yield boundary
				yield b"\r\n".join(part_headers)
				yield snapshot.jpeg
				yield b"\r\n"

		headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
		return StreamingResponse(generator(), media_type="multipart/x-mixed-replace; boundary=frame", headers=headers)

	@app.get("/")
	def index() -> Dict[str, str]:
		return {
			"health": "/health",
			"stream": "/stream",
			"snapshot": "/snapshot.jpg",
			"latest": "/latest",
		}

	return app


app = build_app()


if __name__ == "__main__":
	import uvicorn

	host = os.getenv("HOST", "0.0.0.0")
	port = int(os.getenv("PORT", "8000"))
	uvicorn.run("main:app", host=host, port=port, reload=False)
