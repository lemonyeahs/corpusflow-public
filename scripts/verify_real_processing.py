"""Run real PDF/HTML processing against the local Compose stack."""

import io
import json
import time
import urllib.error
import urllib.request

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

BASE = "http://127.0.0.1:58000/api/v1"
TOKEN = "real-worker-admin"


def call(method: str, path: str, obj: dict | None = None, body: bytes | None = None):
    data = body if body is not None else (json.dumps(obj).encode() if obj else None)
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        print("ERR", method, path, error.code, error.read())
        raise


def make_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 18 Tf 30 200 Td (Hello PDF) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main() -> None:
    call(
        "POST",
        "/auth/session",
        {"user_id": TOKEN, "display_name": "Real Worker", "workspace_name": "Real Processing"},
    )
    _, source = call("POST", "/sources", {"name": "real-source", "kind": "upload"})
    uploads = [
        ("doc.html", "text/html", b"<h1>HTML title</h1><p>HTML body</p>"),
        ("doc.pdf", "application/pdf", make_pdf()),
        ("bad.pdf", "application/pdf", b"bad pdf"),
    ]
    upload_ids = []
    for filename, media_type, content in uploads:
        _, init = call(
            "POST",
            "/uploads/init",
            {"filename": filename, "size": len(content), "content_type": media_type},
        )
        upload_id = init["upload_id"]
        request = urllib.request.Request(
            f"{BASE}/uploads/{upload_id}/content",
            data=content,
            method="PUT",
            headers={"Content-Type": media_type, "Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            uploaded = json.loads(response.read())
        call("POST", f"/uploads/{upload_id}/complete", {"checksum": uploaded["sha256"]})
        upload_ids.append(upload_id)
    _, ingest = call(
        "POST", "/ingest-batches", {"upload_ids": upload_ids, "source_id": source["source_id"]}
    )
    _, batch = call(
        "POST",
        "/pipeline-runs/batches",
        {"asset_ids": [item["asset_id"] for item in ingest["items"]]},
    )
    states = []
    for _ in range(30):
        states = []
        for accepted in batch["accepted"]:
            _, run = call("GET", f"/pipeline-runs/{accepted['run_id']}")
            states.append((accepted["run_id"], run["status"]))
        print(states)
        if all(status in {"succeeded", "failed"} for _, status in states):
            break
        time.sleep(1)
    print("logs")
    for run_id, _ in states:
        print(run_id, call("GET", f"/pipeline-runs/{run_id}/logs")[1])


if __name__ == "__main__":
    main()
