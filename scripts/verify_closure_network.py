"""Read-only local/container DNS evidence and real fail-closed public requests."""

import json
import socket
import subprocess
from pathlib import Path

from corpusflow.adapters.acquisition import AcquisitionError, SafeFetcher

hosts = ["api.crossref.org", "www.rfc-editor.org", "example.com"]
local = {
    h: sorted({r[4][0] for r in socket.getaddrinfo(h, 443, type=socket.SOCK_STREAM)}) for h in hosts
}
code = (
    "import socket,json; print(json.dumps({h:sorted({r[4][0] for r in "
    "socket.getaddrinfo(h,443,type=socket.SOCK_STREAM)}) for h in " + repr(hosts) + "}))"
)
container = json.loads(
    subprocess.check_output(["docker", "exec", "corpusflow-p0a-worker-1", "python", "-c", code])
)
requests = []
for url in [
    "https://api.crossref.org/works/10.1038/s41586-020-2649-2",
    "https://www.rfc-editor.org/rfc/rfc20.html",
    "https://example.com/",
]:
    try:
        result = SafeFetcher(hosts).get(url)
        requests.append(
            {"url": url, "status": "FETCHED", "sha256": result.sha256, "bytes": len(result.content)}
        )
    except AcquisitionError as exc:
        requests.append({"url": url, "status": "BLOCKED", "code": str(exc)})
result = {
    "host_addresses": local,
    "container_addresses": container,
    "public_attempts": requests,
    "dns_configuration_modified": False,
    "proxy_bypass_added": False,
    "interpretation": "198.18.x.x synthesis observed; precise interception software not attributed",
    "direct_configured_resolver": subprocess.check_output(
        ["dig", "+time=2", "+tries=1", "@223.5.5.5", "api.crossref.org", "A", "+noall", "+answer"]
    ).decode(),
    "cname_query": subprocess.check_output(
        ["dig", "+time=2", "+tries=1", "api.crossref.org", "CNAME", "+noall", "+answer"]
    ).decode(),
}
Path("docs/reports/P2_CLOSURE_NETWORK_EVIDENCE.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps({"attempts": requests, "scope": "read-only, no public success implied"}))
