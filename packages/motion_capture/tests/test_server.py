from fastapi.testclient import TestClient

from motion_capture.server import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_websocket_connection():
    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/capture") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data["type"] == "pong"
        websocket.send_json({"type": "start_recording"})
        started = websocket.receive_json()
        assert started["type"] == "recording_started"
        websocket.send_json({"type": "stop_recording"})
        stopped = websocket.receive_json()
        assert stopped["type"] == "recording_stopped"
        assert isinstance(stopped["landmarks_frames"], list)

