"""One-time: obtain a Gmail refresh token with the narrowest scope (send only).
Usage: GMAIL_CLIENT_ID=... GMAIL_CLIENT_SECRET=... python scripts/gmail_auth.py
Create an OAuth client (type: Desktop app) in Google Cloud Console and enable the Gmail API first."""
import http.server, os, urllib.parse, requests, webbrowser

CID, SEC = os.environ["GMAIL_CLIENT_ID"], os.environ["GMAIL_CLIENT_SECRET"]
REDIRECT = "http://localhost:8765"
url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": CID, "redirect_uri": REDIRECT, "response_type": "code", "access_type": "offline", "prompt": "consent",
    "scope": "https://www.googleapis.com/auth/gmail.send"})
print("Open:", url); webbrowser.open(url)
code = {}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code["v"] = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("code", [""])[0]
        self.send_response(200); self.end_headers(); self.wfile.write(b"Done. You can close this tab.")
    def log_message(self, *a): pass
http.server.HTTPServer(("localhost", 8765), H).handle_request()
r = requests.post("https://oauth2.googleapis.com/token", data={"code": code["v"], "client_id": CID, "client_secret": SEC,
                  "redirect_uri": REDIRECT, "grant_type": "authorization_code"}).json()
print("GMAIL_REFRESH_TOKEN=" + r.get("refresh_token", f"<none: {r}>"))
