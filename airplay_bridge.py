
from http.server import HTTPServer, BaseHTTPRequestHandler
from pynput.keyboard import Controller, Key
import json
import threading
import time

keyboard = Controller()
held_keys = set()
lock = threading.Lock()
last_movement_time = time.time()

DEFAULT_MAPPING = {
    "MOVE_LEFT": "a",
    "MOVE_RIGHT": "d",
    "JUMP": "space",
    "ATTACK": "l",
    "SPECIAL_ACTION": "k",
    "WOOD_HIDDEN_SKILL": "j",
    "PAUSE": "m"
}

KEY_NAMES = {
    "space": Key.space,
    "enter": Key.enter,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "tab": Key.tab,
    "esc": Key.esc,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right
}

def resolve_key(name):
    name = str(name).strip().lower()

    if len(name) == 1 and name.isalnum():
        return name

    return KEY_NAMES.get(name)


def release_all():
    global held_keys

    with lock:
        for key in list(held_keys):
            try:
                keyboard.release(key)
            except Exception:
                pass

        held_keys.clear()


def watchdog():
    global last_movement_time

    while True:
        time.sleep(0.1)

        with lock:
            expired = (
                time.time() - last_movement_time > 0.7
            )

        if expired:
            release_all()


class AirPlayHandler(BaseHTTPRequestHandler):

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_json(200, {"status": "ok"})

    def do_POST(self):

        if self.path != "/gesture":
            self.send_json(404, {"error": "Unknown endpoint"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))

            gestures = data.get("gestures", [])
            mapping = data.get("keyMapping", DEFAULT_MAPPING)

            if not isinstance(gestures, list):
                raise ValueError("Gestures must be a list")

            if not isinstance(mapping, dict):
                raise ValueError("Invalid key mapping")

            if "READY" in gestures:
                release_all()
                self.send_json(200, {"status": "ready"})
                return

            if "PAUSE" in gestures:
                release_all()
                key = resolve_key(mapping.get("PAUSE", "m"))
                if key is not None:
                    keyboard.press(key)
                    keyboard.release(key)
                self.send_json(200, {"status": "pause"})
                return

            allowed = set(DEFAULT_MAPPING.keys())

            for gesture in gestures:
                if gesture not in allowed:
                    continue

            movement_names = {"MOVE_LEFT", "MOVE_RIGHT"}
            requested_movement = {
                mapping.get(g)
                for g in gestures
                if g in movement_names
            }

            requested_movement = {
                resolve_key(k) for k in requested_movement
            }

            requested_movement.discard(None)

            with lock:
                global last_movement_time

                last_movement_time = time.time()

                for key in list(held_keys):
                    if key not in requested_movement:
                        keyboard.release(key)
                        held_keys.remove(key)

                for key in requested_movement:
                    if key not in held_keys:
                        keyboard.press(key)
                        held_keys.add(key)

            for gesture in gestures:
                if gesture in movement_names or gesture == "READY":
                    continue

                if gesture not in allowed:
                    continue

                key = resolve_key(mapping.get(
                    gesture,
                    DEFAULT_MAPPING[gesture]
                ))

                if key is not None:
                    keyboard.press(key)
                    keyboard.release(key)

            print("Received:", gestures)

            self.send_json(200, {"status": "success"})

        except Exception as error:
            print("Error:", error)
            self.send_json(400, {"error": str(error)})


if __name__ == "__main__":

    threading.Thread(
        target=watchdog,
        daemon=True
    ).start()

    server = HTTPServer(
        ("127.0.0.1", 5000),
        AirPlayHandler
    )

    print("AirPlay bridge running at http://127.0.0.1:5000")
    server.serve_forever()
