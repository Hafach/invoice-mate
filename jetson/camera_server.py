#!/usr/bin/env python3
"""Invoice camera station for the Jetson.

Serves the camera to the laptop over HTTP (no extra packages, only OpenCV):
  GET /stream    live MJPEG preview (for the web UI)
  GET /snapshot  one full-quality JPEG (what the agent reads)
  GET /health    JSON: camera ok, resolution, sharpness score

Run:  python3 camera_server.py            (auto-detects USB, then CSI camera)
      CAMERA=csi python3 camera_server.py
      CAMERA=1 PORT=8090 python3 camera_server.py
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

PORT = int(os.environ.get("PORT", "8090"))
HOST = os.environ.get("HOST", "127.0.0.1")  # only the app on the Jetson needs the camera; set 0.0.0.0 to expose it
CAMERA = os.environ.get("CAMERA", "auto")  # auto | csi | <index>
WIDTH = int(os.environ.get("WIDTH", "1920"))
HEIGHT = int(os.environ.get("HEIGHT", "1080"))
BLUR_THRESHOLD = float(os.environ.get("BLUR_THRESHOLD", "60"))


def csi_pipeline(w, h):
    return (
        f"nvarguscamerasrc ! video/x-raw(memory:NVMM), width={w}, height={h}, framerate=30/1 ! "
        "nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! video/x-raw, format=BGR ! "
        "appsink drop=true max-buffers=1"
    )


def open_camera():
    attempts = []
    if CAMERA == "csi":
        attempts = [("csi", lambda: cv2.VideoCapture(csi_pipeline(WIDTH, HEIGHT), cv2.CAP_GSTREAMER))]
    elif CAMERA.isdigit():
        attempts = [(f"usb{CAMERA}", lambda: cv2.VideoCapture(int(CAMERA), cv2.CAP_V4L2))]
    else:
        for i in range(4):
            if os.path.exists(f"/dev/video{i}"):
                attempts.append((f"usb{i}", lambda i=i: cv2.VideoCapture(i, cv2.CAP_V4L2)))
        attempts.append(("csi", lambda: cv2.VideoCapture(csi_pipeline(WIDTH, HEIGHT), cv2.CAP_GSTREAMER)))
    for name, make in attempts:
        cap = make()
        if not cap.isOpened():
            cap.release()
            continue
        if name.startswith("usb"):
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, frame = cap.read()
        if ok and frame is not None:
            print(f"[camera] using {name} at {frame.shape[1]}x{frame.shape[0]}", flush=True)
            return name, cap
        cap.release()
    raise SystemExit("[camera] no working camera found (tried: %s)" % [a[0] for a in attempts])


class Camera:
    def __init__(self):
        self.name, self.cap = open_camera()
        self.lock = threading.Lock()
        self.frame = None
        self.frame_time = 0.0
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        fails = 0
        while True:
            ok, frame = self.cap.read()
            if ok and frame is not None:
                fails = 0
                with self.lock:
                    self.frame, self.frame_time = frame, time.time()
            else:
                fails += 1
                time.sleep(0.05)
                if fails > 100:  # camera unplugged / stalled: reopen
                    print("[camera] reopening", flush=True)
                    self.cap.release()
                    self.name, self.cap = open_camera()
                    fails = 0

    def latest(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy(), self.frame_time


def sharpness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (960, int(960 * gray.shape[0] / gray.shape[1])))
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


CAM = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            frame, t = CAM.latest()
            body = {
                "ok": frame is not None and time.time() - t < 3,
                "camera": CAM.name,
                "resolution": None if frame is None else [frame.shape[1], frame.shape[0]],
                "sharpness": None if frame is None else round(sharpness(frame), 1),
                "blur_threshold": BLUR_THRESHOLD,
            }
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        elif path == "/snapshot":
            frame, _ = CAM.latest()
            if frame is None:
                self.send_error(503, "no frame yet")
                return
            score = sharpness(frame)
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("X-Sharpness", f"{score:.1f}")
            self.send_header("X-Blurry", "1" if score < BLUR_THRESHOLD else "0")
            self.send_header("Access-Control-Expose-Headers", "X-Sharpness, X-Blurry")
            self._cors()
            self.end_headers()
            self.wfile.write(jpg.tobytes())
        elif path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self._cors()
            self.end_headers()
            last = 0.0
            try:
                while True:
                    frame, t = CAM.latest()
                    if frame is None or t == last:
                        time.sleep(0.03)
                        continue
                    last = t
                    preview = cv2.resize(frame, (960, int(960 * frame.shape[0] / frame.shape[1])))
                    ok, jpg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
                    time.sleep(0.06)  # ~15 fps preview
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


if __name__ == "__main__":
    CAM = Camera()
    print(f"[camera] serving on {HOST}:{PORT}  (/stream /snapshot /health)", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
