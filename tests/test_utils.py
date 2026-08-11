import base64
import json

from app import parse_service_account_json, normalize_rows


def test_parse_service_account_json_plain():
    sample = json.dumps({"type": "service_account", "client_email": "a@b.iam.gserviceaccount.com", "private_key": "----"})
    parsed = parse_service_account_json(sample)
    assert isinstance(parsed, dict)
    assert parsed["type"] == "service_account"


def test_parse_service_account_json_base64():
    obj = {"type": "service_account", "client_email": "a@b.iam.gserviceaccount.com", "private_key": "----"}
    encoded = base64.b64encode(json.dumps(obj).encode("utf-8")).decode("utf-8")
    parsed = parse_service_account_json(encoded)
    assert isinstance(parsed, dict)
    assert parsed["client_email"] == obj["client_email"]


def test_normalize_rows_list_of_lists():
    rows = [["Campaign Name", "Link"], ["Test Camp", "https://example.com"]]
    normalized = normalize_rows(rows)
    assert len(normalized) == 1
    assert normalized[0]["name"] == "Test Camp"


def test_normalize_rows_dicts():
    rows = [{"Campaign Name": "Camp X", "URL": "https://x"}, {"Campaign Name": "", "URL": ""}]
    normalized = normalize_rows(rows)
    assert len(normalized) == 1
    assert normalized[0]["link"] == "https://x"
