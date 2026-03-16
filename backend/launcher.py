import os
import socket
import threading
import time
import traceback
import webbrowser

from app import app


def _wait_for_server(host: str, port: int, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _open_browser_when_ready(url: str, host: str, port: int) -> None:
    if _wait_for_server(host, port):
        webbrowser.open(url)


def main() -> None:
    host = os.getenv("RA_HOST", "127.0.0.1")
    port = int(os.getenv("RA_PORT", os.getenv("PORT", "5000")))
    app.debug = False

    url = f"http://{host}:{port}"
    threading.Thread(
        target=_open_browser_when_ready,
        args=(url, host, port),
        daemon=True,
    ).start()

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    except Exception:
        log_path = os.path.join(os.getcwd(), "ra-launcher-error.log")
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
