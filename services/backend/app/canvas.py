import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from .db import now
from .models import Connector, Course
from .schemas import IngestInput
from .security import vault
from .reasoning import ingest, process


def public_origin(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Canvas 地址必须是 HTTPS 公网域名，如 https://school.instructure.com")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Canvas 地址不可指向本地或内网")
    return f"https://{parsed.hostname}"


def pages(client, origin, path, params=None):
    url = origin + path
    for _ in range(100):
        # Never forward bearer tokens to cross-origin pagination or redirects.
        if not url.startswith(origin + "/api/v1/"):
            raise ValueError("Unexpected Canvas pagination origin")
        response = client.get(url, params=params)
        response.raise_for_status()
        yield from response.json()
        url = response.links.get("next", {}).get("url")
        if not url:
            return
        params = None
    raise ValueError("Canvas pagination exceeded safe limit")


def sync(db, connector):
    try:
        origin = public_origin(connector.base_url)
        token = vault().decrypt(connector.encrypted_token.encode()).decode()
        count = 0
        with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30, follow_redirects=False) as client:
            courses = list(pages(client, origin, "/api/v1/courses", {"enrollment_state": "active", "per_page": 100}))
            for course in courses:
                if "name" not in course:
                    continue
                course_id = str(course["id"])
                local = db.scalar(select(Course).where(Course.user_id == connector.user_id, Course.connector_id == connector.id, Course.external_id == course_id))
                if not local:
                    local = Course(user_id=connector.user_id, connector_id=connector.id, external_id=course_id, name=course["name"])
                    db.add(local)
                local.name = course["name"]
                for assignment in pages(client, origin, f"/api/v1/courses/{course_id}/assignments", {"per_page": 100}):
                    if assignment.get("published") is False:
                        continue
                    raw = ingest(db, connector.user_id, IngestInput(platform="canvas", source_type="assignment",
                        external_id=f"{connector.id}:{course_id}:{assignment['id']}", channel_name=course["name"], title=assignment["name"],
                        content=re.sub("<[^>]+>", " ", assignment.get("description") or assignment["name"]),
                        structured_data={"course_id": local.id, "due_at": assignment.get("due_at")}, source_updated_at=assignment["updated_at"]))
                    if raw.status == "queued":
                        process(db, raw)
                        count += 1
                for item in pages(client, origin, "/api/v1/announcements", {"context_codes[]": f"course_{course_id}", "per_page": 100}):
                    raw = ingest(db, connector.user_id, IngestInput(platform="canvas", source_type="announcement",
                        external_id=f"{connector.id}:announcement:{item['id']}", channel_name=course["name"], title=item["title"],
                        content=re.sub("<[^>]+>", " ", item.get("message") or item["title"]), source_updated_at=item.get("posted_at")))
                    if raw.status == "queued":
                        process(db, raw)
                        count += 1
        connector.last_synced_at = now()
        connector.error = None
        db.flush()
        return {"processed": count}
    except Exception as exc:
        connector.error = f"同步失败（{type(exc).__name__}），请检查学校地址、令牌和网络。"
        db.flush()
        return {"error": connector.error}
