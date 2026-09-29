#!/usr/bin/env python3
"""Local demo company: a careers page (schema.org JSON-LD) + application forms that record submissions.

Lets you try the complete AutoApply AI loop — scan -> match -> tailor -> fill -> approve -> submit —
without sending anything to a real employer.

    python scripts/demo_site.py            # serves http://127.0.0.1:8765
    # then in Settings -> Job sources -> Company careers pages: http://127.0.0.1:8765/careers
    # and enable the "Career pages" platform.

Submissions are printed to stdout and listed at http://127.0.0.1:8765/submissions
"""

from __future__ import annotations

import argparse
import cgi
import html
import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JOBS = [
    {
        "id": "1", "title": "Software Engineer, Backend", "location": ("San Francisco", "CA"), "remote": False,
        "salary": (150000, 190000),
        "description": "Acme Robotics builds developer tools used by millions of engineers. Our mission is to make "
                       "robot fleets as easy to program as a web app. You will design REST APIs in Python and FastAPI, "
                       "own PostgreSQL schemas, and ship services on Docker and Kubernetes (AWS). 2+ years of "
                       "backend experience required. Nice to have: Redis, Celery, observability.",
    },
    {
        "id": "2", "title": "Full-Stack Engineer (React + Python)", "location": ("Remote", "US"), "remote": True,
        "salary": (140000, 175000),
        "description": "We are looking for a full-stack engineer comfortable with React, TypeScript and Python. "
                       "You'll build our customer dashboard end to end. 3+ years of experience. Remote-first team.",
    },
    {
        "id": "3", "title": "Senior iOS Engineer", "location": ("New York", "NY"), "remote": False,
        "salary": (180000, 230000),
        "description": "7+ years building iOS apps in Swift and SwiftUI. Deep knowledge of Objective-C, Core Data "
                       "and App Store release processes.",
    },
]

FORM = """<!doctype html><html><head><title>Apply — {title}</title>
<style>body{{font-family:system-ui;max-width:720px;margin:40px auto;padding:0 16px;color:#111}}
label{{display:block;margin-top:14px;font-weight:600}}input,select,textarea{{width:100%;padding:8px;margin-top:4px;box-sizing:border-box}}
textarea{{min-height:90px}}.row label{{display:inline;font-weight:400;margin-right:12px}}.row input{{width:auto}}
button{{margin-top:20px;padding:10px 18px;background:#4f46e5;color:#fff;border:0;border-radius:6px;font-size:15px}}</style></head>
<body><h1>{title}</h1><p>Acme Robotics · {location}</p><p>{description}</p>
<form id="application-form" method="post" action="/jobs/{id}/submit" enctype="multipart/form-data">
<label for="first_name">First Name *</label><input id="first_name" name="first_name" required>
<label for="last_name">Last Name *</label><input id="last_name" name="last_name" required>
<label for="email">Email *</label><input id="email" name="email" type="email" required>
<label for="phone">Phone</label><input id="phone" name="phone" type="tel">
<label for="resume">Resume/CV *</label><input id="resume" name="resume" type="file" required>
<label for="cover_letter">Cover Letter</label><textarea id="cover_letter" name="cover_letter"></textarea>
<label for="linkedin">LinkedIn Profile</label><input id="linkedin" name="linkedin">
<div class="field"><div class="label"><b>Are you legally authorized to work in the United States? *</b></div>
<div class="row"><label><input type="radio" name="auth" value="yes" required> Yes</label><label><input type="radio" name="auth" value="no"> No</label></div></div>
<label for="sponsor">Will you now or in the future require visa sponsorship? *</label>
<select id="sponsor" name="sponsor" required><option value="">Select...</option><option>Yes</option><option>No</option></select>
<label for="salary">What are your salary expectations?</label><input id="salary" name="salary">
<label for="why">Why do you want to work at Acme Robotics? *</label><textarea id="why" name="why" required></textarea>
<label for="gender">Gender (voluntary)</label>
<select id="gender" name="gender"><option value="">Select...</option><option>Male</option><option>Female</option><option>Non-binary</option><option>Decline To Self Identify</option></select>
<div class="row" style="margin-top:14px"><label><input type="checkbox" name="consent" required> I agree to the privacy policy *</label></div>
<button type="submit">Submit application</button></form></body></html>"""


class DemoSite(BaseHTTPRequestHandler):
    submissions: list[dict] = []

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass

    def _send(self, body: str, status: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def base(self) -> str:
        return f"http://{self.headers.get('Host', '127.0.0.1:8765')}"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/careers"):
            postings = []
            for job in JOBS:
                city, region = job["location"]
                postings.append({
                    "@context": "https://schema.org", "@type": "JobPosting", "title": job["title"],
                    "description": f"<p>{html.escape(job['description'])}</p>",
                    "datePosted": (datetime.now(UTC) - timedelta(days=2)).date().isoformat(),
                    "employmentType": "FULL_TIME",
                    "hiringOrganization": {"@type": "Organization", "name": "Acme Robotics"},
                    "jobLocation": {"@type": "Place", "address": {"addressLocality": city, "addressRegion": region}},
                    **({"jobLocationType": "TELECOMMUTE"} if job["remote"] else {}),
                    "baseSalary": {"@type": "MonetaryAmount", "currency": "USD", "value": {
                        "@type": "QuantitativeValue", "minValue": job["salary"][0], "maxValue": job["salary"][1], "unitText": "YEAR"}},
                    "url": f"{self.base()}/jobs/{job['id']}", "directApplyUrl": f"{self.base()}/jobs/{job['id']}/apply",
                })
            items = "".join(f'<li><a href="/jobs/{j["id"]}">{html.escape(j["title"])}</a></li>' for j in JOBS)
            self._send(f'<html><head><title>Careers at Acme Robotics</title><script type="application/ld+json">'
                       f'{json.dumps({"@context": "https://schema.org", "@graph": postings})}</script></head>'
                       f"<body><h1>Careers at Acme Robotics</h1><ul>{items}</ul></body></html>")
        elif path.startswith("/jobs/"):
            job = next((j for j in JOBS if j["id"] == path.split("/")[2]), None)
            if job is None:
                return self._send("Not found", 404)
            city, region = job["location"]
            self._send(FORM.format(id=job["id"], title=html.escape(job["title"]), location=f"{city}, {region}",
                                   description=html.escape(job["description"])))
        elif path == "/submissions":
            self._send(json.dumps(self.submissions, indent=2), ctype="application/json")
        else:
            self._send("Not found", 404)

    def do_POST(self) -> None:  # noqa: N802
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        record: dict = {"job_id": self.path.split("/")[2], "received_at": datetime.now(UTC).isoformat()}
        for key in form.keys():
            item = form[key]
            record[key] = {"filename": item.filename, "bytes": len(item.value)} if item.filename else item.value
        self.submissions.append(record)
        print("NEW APPLICATION:", json.dumps(record, indent=2), flush=True)
        number = f"ACME-{1000 + len(self.submissions)}"
        self._send(f"<html><body><h1>Thank you for applying!</h1><p>Your application has been submitted. "
                   f"Confirmation number: {number}</p></body></html>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoSite)
    print(f"Demo careers site: http://{args.host}:{args.port}/careers  (submissions: /submissions)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
