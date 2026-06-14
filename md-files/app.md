"""Optional AppDynamics integration.

Pulls a crash stacktrace by crash id. Uses the controller `restui` download
endpoint, the same one the AppDynamics web UI calls:

    GET {controller}/controller/restui/crashDetails/download/{appId}/{crashId}
    Authorization: Bearer <token>

IMPORTANT: restui endpoints are not an officially stable public API. They work
today but can change between controller versions. Confirm against your own
controller before depending on this in production. If your org exposes the
documented Analytics/Events API instead, swap the URL here.
"""
import os
import requests


def is_configured() -> bool:
return bool(
os.environ.get("APPD_CONTROLLER_URL")
and os.environ.get("APPD_ACCESS_TOKEN")
and os.environ.get("APPD_APP_ID")
)


def fetch_crash_trace(crash_id: str) -> str:
base = os.environ["APPD_CONTROLLER_URL"].rstrip("/")
app_id = os.environ["APPD_APP_ID"]
token = os.environ["APPD_ACCESS_TOKEN"]
url = f"{base}/controller/restui/crashDetails/download/{app_id}/{crash_id}"
resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
resp.raise_for_status()
return resp.text
