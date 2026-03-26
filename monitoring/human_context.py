# monitoring/human_context.py

import os
import cv2
import base64
import threading
import time
import numpy as np

# ----------------------------
# Config
# ----------------------------
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
FRAME_WIDTH = int(os.getenv("HUMAN_CONTEXT_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("HUMAN_CONTEXT_HEIGHT", "480"))
FRAME_SLEEP = float(os.getenv("HUMAN_CONTEXT_SLEEP", "0.04"))

# how many matched frames before a box is considered stable
STABLE_HITS = int(os.getenv("HUMAN_CONTEXT_STABLE_HITS", "3"))

# allow a track to survive short missed detections
MAX_MISSES = int(os.getenv("HUMAN_CONTEXT_MAX_MISSES", "12"))

# IoU threshold for matching current detections to old tracks
IOU_MATCH_THRESHOLD = float(os.getenv("HUMAN_CONTEXT_IOU", "0.30"))

# smooth box movement
SMOOTHING_ALPHA = float(os.getenv("HUMAN_CONTEXT_SMOOTHING", "0.70"))

# detect every frame by default
DETECTION_EVERY_N_FRAMES = int(os.getenv("HUMAN_CONTEXT_DETECT_EVERY", "1"))

# ----------------------------
# Shared state
# ----------------------------
_lock = threading.Lock()

_state = {
    "people_detected": 0,   # stable boxes only
    "motion_score": 0.0,
    "camera_ok": False,
    "image": None,
}

_thread = None
_stop_event = threading.Event()
_capture = None
_track_id_counter = 0

# ----------------------------
# Detectors
# ----------------------------
_face_detector = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


# ----------------------------
# Helpers
# ----------------------------
def _next_track_id():
    global _track_id_counter
    _track_id_counter += 1
    return _track_id_counter


def _encode_frame(frame):
    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        return None
    return base64.b64encode(buffer).decode("utf-8")


def _compute_motion(prev_gray, gray):
    diff = cv2.absdiff(prev_gray, gray)
    return float(np.mean(diff)) / 255.0


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter = inter_w * inter_h

    if inter <= 0:
        return 0.0

    area_a = aw * ah
    area_b = bw * bh
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0

    return float(inter) / float(union)


def _smooth_bbox(old_box, new_box, alpha=SMOOTHING_ALPHA):
    ox, oy, ow, oh = old_box
    nx, ny, nw, nh = new_box

    x = alpha * ox + (1.0 - alpha) * nx
    y = alpha * oy + (1.0 - alpha) * ny
    w = alpha * ow + (1.0 - alpha) * nw
    h = alpha * oh + (1.0 - alpha) * nh

    return int(x), int(y), int(w), int(h)


def _detect_faces(gray):
    faces = _face_detector.detectMultiScale(
        gray,
        scaleFactor=1.15,
        minNeighbors=5,
        minSize=(30, 30),
    )
    return [tuple(map(int, f)) for f in faces]


def _detect_people(frame):
    rects, _ = _hog.detectMultiScale(
        frame,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
    )
    return [tuple(map(int, r)) for r in rects]


def _dedupe_person_boxes(face_boxes, body_boxes):
    """
    Prefer face boxes.
    Add body boxes only if they do not strongly overlap with a face box.
    """
    merged = list(face_boxes)

    for b in body_boxes:
        overlap = False
        for f in face_boxes:
            if _iou(b, f) >= 0.20:
                overlap = True
                break
        if not overlap:
            merged.append(b)

    return merged


def _detect_label(box):
    # faces are preferred, but if a box exists it is a person-context box
    return "person"


def _match_tracks(tracks, detections):
    """
    Greedy IoU matching.
    A track becomes 'stable' only after it survives STABLE_HITS matches.
    """
    used_dets = set()

    for t in tracks:
        best_iou = 0.0
        best_idx = -1

        for i, det in enumerate(detections):
            if i in used_dets:
                continue

            score = _iou(t["bbox"], det)
            if score > best_iou:
                best_iou = score
                best_idx = i

        if best_idx >= 0 and best_iou >= IOU_MATCH_THRESHOLD:
            det = detections[best_idx]
            t["bbox"] = _smooth_bbox(t["bbox"], det)
            t["misses"] = 0
            t["hits"] += 1
            t["stable"] = t["hits"] >= STABLE_HITS
            used_dets.add(best_idx)
        else:
            t["misses"] += 1

    # Remove stale tracks
    tracks[:] = [t for t in tracks if t["misses"] <= MAX_MISSES]

    # Create tracks for unmatched detections
    for i, det in enumerate(detections):
        if i in used_dets:
            continue

        tracks.append(
            {
                "id": _next_track_id(),
                "bbox": det,
                "misses": 0,
                "hits": 1,
                "stable": False,
                "label": _detect_label(det),
            }
        )


def _draw_tracks(frame, tracks):
    # draw only stable boxes so UI shows steady green boxes
    for t in tracks:
        if not t.get("stable", False):
            continue

        x, y, w, h = t["bbox"]
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)


def _loop():
    global _capture

    _capture = cv2.VideoCapture(CAMERA_INDEX)

    if not _capture.isOpened():
        with _lock:
            _state["camera_ok"] = False
        return

    _capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    _capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    prev_gray = None
    tracks = []
    frame_idx = 0

    while not _stop_event.is_set():
        ok, frame = _capture.read()

        if not ok or frame is None:
            with _lock:
                _state["camera_ok"] = False
            time.sleep(0.1)
            continue

        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        motion_score = 0.0
        if prev_gray is not None:
            motion_score = _compute_motion(prev_gray, gray)
        prev_gray = gray

        if frame_idx % DETECTION_EVERY_N_FRAMES == 0:
            face_boxes = _detect_faces(gray)
            body_boxes = _detect_people(frame)
            detections = _dedupe_person_boxes(face_boxes, body_boxes)
            _match_tracks(tracks, detections)

        frame_idx += 1

        _draw_tracks(frame, tracks)

        stable_people = sum(1 for t in tracks if t.get("stable", False))

        encoded = _encode_frame(frame)

        with _lock:
            _state.update(
                {
                    "people_detected": int(stable_people),  # stable boxes only
                    "motion_score": float(motion_score),
                    "camera_ok": True,
                    "image": encoded,
                }
            )

        time.sleep(FRAME_SLEEP)

    try:
        _capture.release()
    except Exception:
        pass


def start_human_context():
    global _thread

    if _thread and _thread.is_alive():
        return

    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop_human_context():
    _stop_event.set()


def get_human_context():
    with _lock:
        return dict(_state)


def get_latest_frame():
    with _lock:
        return _state.get("image")