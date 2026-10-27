"""
Google Drive upload via REST API (no SDK required).

Uses OAuth2 with refresh token for authentication.
Upload flow: get access token -> resumable upload -> return file URL.
"""

import os
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_FILE = Path(__file__).parent.parent.parent / "data" / ".gdrive_token.json"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


def _load_tokens() -> dict:
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            return json.load(f)
    return {}


def _save_tokens(tokens: dict):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def _refresh_access_token() -> str:
    tokens = _load_tokens()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "No GDrive refresh token. Run: python3 -m backend.pipeline.gdrive_auth"
        )

    result = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "https://oauth2.googleapis.com/token",
            "-d", f"client_id={GOOGLE_CLIENT_ID}",
            "-d", f"client_secret={GOOGLE_CLIENT_SECRET}",
            "-d", f"refresh_token={refresh_token}",
            "-d", "grant_type=refresh_token",
        ],
        capture_output=True, text=True,
    )

    data = json.loads(result.stdout)
    if "access_token" not in data:
        raise RuntimeError(f"Failed to refresh token: {data}")

    tokens["access_token"] = data["access_token"]
    _save_tokens(tokens)
    return data["access_token"]


async def upload_to_gdrive(
    file_path: str,
    folder_id: str = None,
    delete_after: bool = False,
) -> dict:
    """
    Upload a file to Google Drive.

    Returns:
        dict with id, name, webViewLink, size_mb
    """
    import asyncio

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    access_token = _refresh_access_token()
    file_size = file_path.stat().st_size
    mime_type = _guess_mime(file_path)

    logger.info(f"Uploading {file_path.name} ({file_size / 1024 / 1024:.0f} MB) to GDrive...")

    # Step 1: Initiate resumable upload
    metadata = {"name": file_path.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    result = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
            "-H", f"Authorization: Bearer {access_token}",
            "-H", "Content-Type: application/json; charset=UTF-8",
            "-H", f"X-Upload-Content-Type: {mime_type}",
            "-H", f"X-Upload-Content-Length: {file_size}",
            "-d", json.dumps(metadata),
            "-D", "-",
        ],
        capture_output=True, text=True,
    )

    # Extract upload URI from Location header
    upload_uri = None
    for line in result.stdout.split("\n"):
        if line.lower().startswith("location:"):
            upload_uri = line.split(":", 1)[1].strip()
            break

    if not upload_uri:
        raise RuntimeError(f"Failed to initiate upload: {result.stdout[:500]}")

    # Step 2: Upload file content
    upload_result = await asyncio.to_thread(
        _upload_file_content, upload_uri, file_path, mime_type, access_token
    )

    data = json.loads(upload_result)
    file_id = data.get("id")
    if not file_id:
        raise RuntimeError(f"Upload failed: {data}")

    # Step 3: Make file viewable by link
    subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            "-H", f"Authorization: Bearer {access_token}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"role": "reader", "type": "anyone"}),
        ],
        capture_output=True,
    )

    web_link = f"https://drive.google.com/file/d/{file_id}/view"
    size_mb = file_size / (1024 * 1024)
    logger.info(f"Uploaded: {file_path.name} ({size_mb:.0f} MB) -> {web_link}")

    if delete_after:
        file_path.unlink()
        logger.info(f"Deleted local file: {file_path}")

    return {
        "id": file_id,
        "name": file_path.name,
        "webViewLink": web_link,
        "size_mb": round(size_mb, 1),
    }


def _upload_file_content(upload_uri, file_path, mime_type, token):
    result = subprocess.run(
        [
            "curl", "-s", "-X", "PUT",
            upload_uri,
            "-H", f"Authorization: Bearer {token}",
            "-H", f"Content-Type: {mime_type}",
            "--data-binary", f"@{file_path}",
        ],
        capture_output=True, text=True,
    )
    return result.stdout


def _guess_mime(path):
    ext = path.suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".json": "application/json",
        ".txt": "text/plain",
    }.get(ext, "application/octet-stream")
