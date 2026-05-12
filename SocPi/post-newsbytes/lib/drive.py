"""Resolve a column-C hyperlink → fetch Doc body + first image.

The cell hyperlink can point to:

  - A Google Drive folder (most common per the team's workflow)
      https://drive.google.com/drive/folders/<FOLDER_ID>
  - A Google Doc directly
      https://docs.google.com/document/d/<DOC_ID>/...

We resolve the type, list the folder if it's a folder, pick the Doc + image
files, then read the Doc body and download the image to cache/.

The Doc body's trailing block has a known shape:

    Social media title: ...
    Social media text: <the caption — possibly multi-paragraph>
    Picture image: ...
    Key words: kw1, kw2, kw3, ...
    Category: ...
    Image source: ...

We extract `Social media text` and `Key words` (case-insensitive label match,
hard-coded labels — keep in sync with the team's Doc template).
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from lib import auth

DOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")
FOLDER_ID_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
DRIVE_FILE_ID_RE = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
OPEN_ID_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")

IMAGE_MIME_PREFIXES = ("image/",)
GDOC_MIME = "application/vnd.google-apps.document"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC_MIMES = (GDOC_MIME, DOCX_MIME)


def fetch(secrets: dict, drive_url: str, row: int) -> dict:
    creds = auth.google_credentials(secrets)
    drive_api = build("drive", "v3", credentials=creds, cache_discovery=False)
    docs_api = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc_id, doc_mime, image_file_id = _resolve_targets(drive_api, drive_url)
    if not doc_id:
        raise SystemExit(
            f"Could not find a Google Doc or .docx at {drive_url}. "
            "The folder must contain a native Google Doc or a Word .docx file."
        )
    if doc_mime == GDOC_MIME:
        body_text = _read_gdoc_body(docs_api, doc_id)
        has_inline = _gdoc_has_inline_image(docs_api, doc_id)
    elif doc_mime == DOCX_MIME:
        body_text = _read_docx_body(drive_api, doc_id)
        has_inline = False  # python-docx inline image extraction is a TODO
    else:
        raise SystemExit(f"Unsupported document mimeType: {doc_mime}")
    social_text, keywords = _parse_trailing_block(body_text)
    image_path = None
    if image_file_id:
        image_path = _download_image(drive_api, image_file_id, row)
    elif has_inline:
        print(f"[drive] Doc has inline image(s) but no separate image file in the folder. "
              f"Inline-image extraction is not supported — please attach the image manually.")
    else:
        print(f"[drive] No image found at {drive_url}. Caption-only post.")
    return {
        "social_media_text": social_text,
        "keywords": keywords,
        "image_path": str(image_path) if image_path else "",
        "drive_image_id": image_file_id or "",
    }


# ---------------------------------------------------------------------------
# Resolve folder vs Doc vs file URL into (doc_id, doc_mime, image_file_id)
# ---------------------------------------------------------------------------

def _resolve_targets(drive_api, drive_url: str) -> tuple[str | None, str | None, str | None]:
    # Native Google Doc URL
    m = DOC_ID_RE.search(drive_url)
    if m:
        return m.group(1), GDOC_MIME, None
    # Folder URL — list contents and pick the Doc + first image
    m = FOLDER_ID_RE.search(drive_url) or OPEN_ID_RE.search(drive_url)
    folder_id = m.group(1) if m else None
    if folder_id:
        return _list_folder(drive_api, folder_id)
    # Direct file URL — could be a Doc-as-file or .docx
    m = DRIVE_FILE_ID_RE.search(drive_url)
    if m:
        file_id = m.group(1)
        meta = drive_api.files().get(fileId=file_id, fields="id, mimeType", supportsAllDrives=True).execute()
        mt = meta.get("mimeType") or ""
        if mt in DOC_MIMES:
            return file_id, mt, None
        if mt.startswith("image/"):
            return None, None, file_id
    return None, None, None


def _list_folder(drive_api, folder_id: str) -> tuple[str | None, str | None, str | None]:
    q = f"'{folder_id}' in parents and trashed = false"
    fields = "files(id, name, mimeType, modifiedTime)"
    resp = drive_api.files().list(
        q=q,
        fields=fields,
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    # Prefer native Google Docs; fall back to .docx.
    doc = next((f for f in files if f["mimeType"] == GDOC_MIME), None) \
        or next((f for f in files if f["mimeType"] == DOCX_MIME), None)
    image = next((f for f in files if (f.get("mimeType") or "").startswith("image/")), None)
    return (
        doc["id"] if doc else None,
        doc["mimeType"] if doc else None,
        image["id"] if image else None,
    )


# ---------------------------------------------------------------------------
# Read Doc body — native Google Docs path
# ---------------------------------------------------------------------------

def _read_gdoc_body(docs_api, doc_id: str) -> str:
    doc = docs_api.documents().get(documentId=doc_id).execute()
    body = doc.get("body", {}).get("content", [])
    parts: list[str] = []
    for block in body:
        para = block.get("paragraph")
        if not para:
            continue
        line = "".join(
            elem.get("textRun", {}).get("content", "")
            for elem in para.get("elements", [])
        )
        parts.append(line)
    return "".join(parts)


def _gdoc_has_inline_image(docs_api, doc_id: str) -> bool:
    doc = docs_api.documents().get(documentId=doc_id).execute()
    objs = doc.get("inlineObjects") or {}
    return bool(objs)


# ---------------------------------------------------------------------------
# Read Doc body — .docx (Word) path
# ---------------------------------------------------------------------------

def _read_docx_body(drive_api, file_id: str) -> str:
    """Download the .docx via Drive and parse paragraphs with python-docx."""
    from docx import Document  # lazy import — only needed when a .docx shows up

    request = drive_api.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    buf.seek(0)
    doc = Document(buf)
    return "\n".join(p.text for p in doc.paragraphs)


# ---------------------------------------------------------------------------
# Trailing-block parser
# ---------------------------------------------------------------------------

LABEL_SOCIAL = "social media text"
LABEL_KEYWORDS = "key words"
LABEL_PICTURE = "picture image"
LABEL_CATEGORY = "category"
LABEL_IMAGE_SRC = "image source"
LABEL_TITLE = "social media title"

_LABEL_RE = re.compile(
    r"^\s*(social media title|social media text|picture image|key ?words|category|image source)\s*:\s*",
    re.IGNORECASE,
)


def _parse_trailing_block(body: str) -> tuple[str, list[str]]:
    """Walk the doc top→bottom; whenever we see one of the known labels,
    capture everything until the next known label (or EOF) as that field's value.
    """
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in body.splitlines():
        m = _LABEL_RE.match(raw_line)
        if m:
            label = m.group(1).lower().replace(" ", "")
            label = "keywords" if label == "keywords" else label
            current = label
            tail = raw_line[m.end():].strip()
            fields.setdefault(current, [])
            if tail:
                fields[current].append(tail)
            continue
        if current and raw_line.strip():
            fields[current].append(raw_line.rstrip())
    social_text = "\n".join(fields.get("socialmediatext") or []).strip()
    kw_raw = " ".join(fields.get("keywords") or []).strip()
    keywords = [k.strip() for k in re.split(r"[,;•]+", kw_raw) if k.strip()]
    return social_text, keywords


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------

EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _download_image(drive_api, file_id: str, row: int) -> Path:
    meta = drive_api.files().get(fileId=file_id, fields="id, name, mimeType", supportsAllDrives=True).execute()
    mime = meta.get("mimeType", "")
    ext = EXT_BY_MIME.get(mime, "")
    if not ext:
        # Fall back to the file's own extension if present
        name = meta.get("name", "")
        for known in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            if name.lower().endswith(known):
                ext = ".jpg" if known == ".jpeg" else known
                break
        if not ext:
            ext = ".bin"
    out_path = auth.cache_dir() / f"row-{row}{ext}"
    request = drive_api.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    out_path.write_bytes(buf.getvalue())
    return out_path


# ---------------------------------------------------------------------------
# Image upload + sharing (used by lib/share_image.py to keep the heavy
# Drive-write permissions narrowly callable via one whitelisted script).
# ---------------------------------------------------------------------------

def build_drive_api(secrets: dict | None = None, *, full_scope: bool = False):
    """Construct a Drive v3 service object. `full_scope` requests the
    read+write `drive` scope; otherwise the read-only default from auth.py is
    used."""
    from google.oauth2.service_account import Credentials  # lazy import

    s = secrets or auth.load_secrets()
    sa_path = auth._sa_path(s)
    if full_scope:
        creds = Credentials.from_service_account_file(
            str(sa_path),
            scopes=["https://www.googleapis.com/auth/drive"],
        )
    else:
        creds = auth.google_credentials(s)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def share_anyone_with_link(drive_api, file_id: str) -> None:
    """Idempotently make a file readable by anyone with the link.

    No-op (warning printed) if the SA isn't allowed to set permissions on
    the file or if the permission already exists.
    """
    try:
        drive_api.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True,
        ).execute()
    except HttpError as exc:
        msg = str(exc)
        if "already" in msg.lower() or "duplicate" in msg.lower():
            return
        print(f"[drive] share warning on {file_id}: {exc}")


def upload_to_staging(drive_api, local_path: Path, staging_folder_id: str, *, name: str | None = None) -> str:
    """Upload a local file to a staging Drive folder (must be a Shared
    Drive, since service accounts have zero personal-Drive quota).

    If a file with the same name already exists in the folder, its content
    is overwritten (idempotent re-runs). Returns the file_id.
    """
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"image not found: {local_path}")
    target_name = name or local_path.name
    mime = _mime_for(local_path)

    # Look for an existing file with the same name to overwrite (idempotency).
    q = f"'{staging_folder_id}' in parents and name = '{target_name}' and trashed = false"
    existing = drive_api.files().list(
        q=q,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute().get("files", [])

    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=False)
    if existing:
        file_id = existing[0]["id"]
        drive_api.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()
        return file_id
    created = drive_api.files().create(
        body={"name": target_name, "parents": [staging_folder_id]},
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def public_url(file_id: str) -> str:
    """Build the public image URL that SocialPilot fetches. The lh3
    googleusercontent endpoint serves the binary content directly without
    Drive's interstitial confirmation page."""
    return f"https://lh3.googleusercontent.com/d/{file_id}"


def _mime_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")
