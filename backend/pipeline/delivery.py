"""
Final delivery phase: zip workspace → upload to GDrive → notify Telegram.

После того как FCPXML + media готовы — упаковываем папку и отдаём владельцу.
Владелец получает Telegram-сообщение со ссылкой на GDrive.
"""

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID = os.getenv("OWNER_CHAT_ID", "") or os.getenv("OWNER_ID", "")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")

# Файлы которые НЕ включаем в zip (для экономии места):
ZIP_EXCLUDE = {".gdrive_token.json", "checkpoint.json"}


def zip_workspace(workspace: Path, output_zip: Optional[Path] = None) -> Path:
    """Zip the workspace folder (excluding metadata files)."""
    workspace = Path(workspace)
    output_zip = output_zip or workspace.parent / f"{workspace.name}.zip"
    # Медиа (mp4/mp3/png/jpg) уже сжаты — DEFLATE на сотнях клипов жжёт CPU и почти
    # не уменьшает размер (на 331 клипе фаза упаковки висела минутами). Храним медиа
    # без сжатия (STORED, быстро), сжимаем только мелкие текстовые файлы.
    _MEDIA = {".mp4", ".mp3", ".wav", ".png", ".jpg", ".jpeg", ".mov", ".m4a"}
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in workspace.rglob("*"):
            if p.is_dir():
                continue
            if p.name in ZIP_EXCLUDE:
                continue
            rel = p.relative_to(workspace.parent)
            ctype = zipfile.ZIP_STORED if p.suffix.lower() in _MEDIA else zipfile.ZIP_DEFLATED
            zf.write(p, rel, compress_type=ctype)
    logger.info(f"zipped {workspace.name} → {output_zip.name} ({output_zip.stat().st_size/(1024*1024):.1f} MB)")
    return output_zip


async def upload_zip_to_gdrive(zip_path: Path, folder_id: str = None) -> dict:
    """Upload zip to Google Drive, return file metadata with shareable link."""
    from backend.pipeline.gdrive import _refresh_access_token

    folder_id = folder_id or GDRIVE_FOLDER_ID
    if not folder_id:
        raise RuntimeError("GDRIVE_FOLDER_ID not set")

    access_token = _refresh_access_token()

    metadata = {
        "name": zip_path.name,
        "parents": [folder_id],
        "mimeType": "application/zip",
    }

    # Simple multipart upload
    boundary = "yt_factory_boundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: application/zip\r\n\r\n"
    ).encode("utf-8")
    body += zip_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15, read=600, write=600, pool=600)) as client:
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink",
            headers=headers, content=body,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"GDrive upload {resp.status_code}: {resp.text[:300]}")
        file_info = resp.json()

        # Make link accessible by anyone with link
        perm_resp = await client.post(
            f"https://www.googleapis.com/drive/v3/files/{file_info['id']}/permissions",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"role": "reader", "type": "anyone"},
        )
        if perm_resp.status_code not in (200, 201):
            logger.warning(f"Failed to set permission: {perm_resp.status_code} {perm_resp.text[:200]}")

    logger.info(f"GDrive uploaded: {file_info.get('webViewLink')}")
    return file_info


async def notify_telegram(message: str, chat_id: str = None) -> bool:
    """Send a message to owner via Telegram bot."""
    chat_id = chat_id or TELEGRAM_OWNER_ID
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        logger.warning("Telegram not configured — skip notify")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        })
        if resp.status_code != 200:
            logger.error(f"Telegram notify failed: {resp.status_code} {resp.text[:200]}")
            return False
    return True


def build_notification(
    task_meta: dict,
    gdrive_link: str,
    workspace: Path,
) -> str:
    """Build the Telegram notification message."""
    topic = task_meta.get("topic", "?")
    lang = task_meta.get("lang", "?")
    duration = task_meta.get("duration_minutes", "?")

    qa_flags = workspace / "QA-flags.md"
    qa_count = 0
    if qa_flags.exists():
        qa_count = qa_flags.read_text().count("## Сцена")

    metadata_file = list(workspace.glob("metadata_*.json"))
    titles = []
    if metadata_file:
        try:
            md = json.loads(metadata_file[0].read_text(encoding="utf-8"))
            titles = md.get("titles") or md.get("title_variants") or []
        except Exception:
            pass

    title_block = ""
    if titles:
        top = titles[:3]
        title_block = "\n\n<b>Топ-3 названия:</b>\n" + "\n".join(f"  {i+1}. {t}" for i, t in enumerate(top))

    msg = (
        f"<b>✓ Новое видео готово</b>\n\n"
        f"<b>Тема:</b> {topic}\n"
        f"<b>Язык:</b> {lang.upper()} · <b>Длительность:</b> ~{duration} мин\n"
        f"<b>QA-флагов:</b> {qa_count} (клипы для замены)\n\n"
        f'<a href="{gdrive_link}">📦 Скачать zip с GDrive</a>'
        f"{title_block}\n\n"
        f"<i>Двойной клик по open-davinci.command (НЕ по project.fcpxml напрямую — "
        f"иначе DaVinci не найдёт картинки). Лаунчер пропишет абсолютные пути и откроет timeline.</i>"
    )
    return msg


async def deliver(task_workspace: Path, task_meta: dict) -> dict:
    """Full delivery: zip → upload → notify. Returns result dict."""
    workspace = Path(task_workspace)
    if not workspace.exists():
        raise RuntimeError(f"Workspace not found: {workspace}")

    zip_path = zip_workspace(workspace)

    # GDrive — опционально. Если не настроен/упал — НЕ валим пайплайн: zip остаётся
    # рядом с workspace и скачивается с сайта через /download.
    gdrive_link, file_info = "", {}
    try:
        file_info = await upload_zip_to_gdrive(zip_path)
        gdrive_link = file_info.get("webViewLink", "")
    except Exception as e:
        logger.warning(f"GDrive upload пропущен/упал ({e}); zip остаётся для скачивания с сайта")

    try:
        notified = await notify_telegram(
            build_notification(task_meta, gdrive_link or "(скачай с сайта)", workspace))
    except Exception as e:
        logger.warning(f"Telegram-уведомление не отправлено: {e}")
        notified = False

    # Удаляем zip только если он уже залит в GDrive; иначе оставляем для /download
    if gdrive_link:
        try:
            zip_path.unlink()
        except Exception:
            pass

    return {
        "gdrive_file_id": file_info.get("id"),
        "gdrive_link": gdrive_link,
        "zip_path": "" if gdrive_link else str(zip_path),
        "notified": notified,
    }
