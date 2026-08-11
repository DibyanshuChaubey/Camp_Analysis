from app import build_google_api_error_message


def test_build_google_api_error_message_for_connection_error():
    message = build_google_api_error_message(TimeoutError("timed out"))
    assert "internet" in message.lower() or "proxy" in message.lower()


def test_build_google_api_error_message_for_permission_error():
    message = build_google_api_error_message(PermissionError("denied"))
    assert "permission" in message.lower() or "shared" in message.lower()
