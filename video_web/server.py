import http.server
import socketserver
import urllib.parse
import os
import http.cookies


class _LimitedFile:
    """Wrap a file so reads cap at `length` bytes — used for Range responses
    so the SimpleHTTPRequestHandler.copyfile loop stops at the right place."""

    def __init__(self, f, length):
        self.f = f
        self.remaining = length

    def read(self, size=-1):
        if self.remaining <= 0:
            return b""
        if size < 0 or size > self.remaining:
            size = self.remaining
        data = self.f.read(size)
        self.remaining -= len(data)
        return data

    def close(self):
        return self.f.close()

# Parse .env file manually so we don't strictly require 'python-dotenv' package
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        k, v = line.split('=', 1)
                        env_vars[k.strip()] = v.strip()
    return env_vars

ENV = load_env()
# Dev mode — set DEV=true in .env only (never in Cloud Run env vars)
DEV_MODE = ENV.get("DEV", "").lower() in ("1", "true", "yes")
if DEV_MODE:
    print("⚠️  DEV MODE: authentication disabled")

# Cloud Run uses OS environment variables; .env file is for local dev
USER1_NAME = ENV.get("USER1_NAME") or os.environ.get("USER1_NAME", "zoominfo")
USER1_PASS = ENV.get("USER1_PASS") or os.environ.get("USER1_PASS", "zoominfo650!")
USER2_NAME = ENV.get("USER2_NAME") or os.environ.get("USER2_NAME", "demo")
USER2_PASS = ENV.get("USER2_PASS") or os.environ.get("USER2_PASS", "demo250!")
USER3_NAME = ENV.get("USER3_NAME") or os.environ.get("USER3_NAME", "appsflyer")
USER3_PASS = ENV.get("USER3_PASS") or os.environ.get("USER3_PASS", "apps350!")

# Map each user to a tenant (folder under video_web/)
USER_TENANTS = {
    USER1_NAME: "zoominfo",
    USER2_NAME: "the_leadership_blueprint",
    USER3_NAME: "appsflyer",
}

# Course catalog rendered into select.html per tenant
COURSE_MANIFEST = {
    "zoominfo": [
        {"path": "zoominfo/the_autonomous_architect",    "title": "SAP & Coupa Goods Receipt",   "subtitle": "Persona A: The Autonomous Architect",  "icon": "🏛️"},
        {"path": "zoominfo/the_disengaged_kinesthetic",  "title": "SAP & Coupa Goods Receipt",   "subtitle": "Persona B: The Disengaged Kinesthetic", "icon": "⚡"},
        {"path": "zoominfo/the_autonomous_architect_B",  "title": "Building Cultural Awareness", "subtitle": "Persona A: The Autonomous Architect",  "icon": "🎧"},
        {"path": "zoominfo/the_disengaged_kinesthetic_B","title": "Building Cultural Awareness", "subtitle": "Persona B: The Disengaged Kinesthetic", "icon": "🎧"},
    ],
    "the_leadership_blueprint": [
        {"path": "the_leadership_blueprint/architect",   "title": "The Leadership Blueprint",    "subtitle": "Persona A: The Autonomous Architect",  "icon": "🏛️"},
        {"path": "the_leadership_blueprint/disengaged",  "title": "The Leadership Blueprint",    "subtitle": "Persona B: The Disengaged Kinesthetic", "icon": "⚡"},
    ],
    "appsflyer": [
        {"path": "appsflyer/architect",   "title": "Accelerating Sales with AWS", "subtitle": "Persona A: The Autonomous Architect",  "icon": "🏛️"},
        {"path": "appsflyer/disengaged",  "title": "Accelerating Sales with AWS", "subtitle": "Persona B: The Disengaged Kinesthetic", "icon": "⚡"},
    ],
}

# session_id -> tenant
SESSIONS = {}


def render_cards(tenant):
    parts = []
    for c in COURSE_MANIFEST.get(tenant, []):
        parts.append(
            f'        <a href="index.html?persona={c["path"]}" class="persona-card">\n'
            f'            <div class="icon">{c["icon"]}</div>\n'
            f'            <div class="title">{c["title"]}</div>\n'
            f'            <div class="desc">{c["subtitle"]}</div>\n'
            f'        </a>'
        )
    return '\n'.join(parts)


class AuthHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        # Only intercept when a Range was requested (typical for video streaming);
        # otherwise fall through to the parent's behaviour.
        range_header = self.headers.get("Range")
        if not range_header:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            size = fs.st_size
            unit, _, ranges = range_header.partition("=")
            if unit.strip().lower() != "bytes":
                raise ValueError("only byte ranges supported")
            start_str, _, end_str = ranges.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else size - 1
            if end >= size:
                end = size - 1
            if start < 0 or start > end:
                raise ValueError("invalid range")
        except ValueError:
            f.close()
            self.send_response(416, "Range Not Satisfiable")
            self.send_header("Content-Range", f"bytes */{size if 'size' in dir() else 0}")
            self.end_headers()
            return None

        length = end - start + 1
        f.seek(start)

        self.send_response(206, "Partial Content")
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return _LimitedFile(f, length)

    def handle_one_request(self):
        # Browsers routinely drop video range requests when the user
        # navigates between slides. Swallow the resulting socket errors
        # so the server log stays readable.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def session_tenant(self):
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            cookie = http.cookies.SimpleCookie(cookie_header)
            if 'session_id' in cookie:
                return SESSIONS.get(cookie['session_id'].value)
        return None

    def check_auth(self):
        if DEV_MODE:
            return True

        # Allow unauthorized access to resources needed by the login page
        if self.path in ['/login.html', '/assets/logo.png', '/login'] or self.path.startswith('/styles.css'):
            return True

        return self.session_tenant() is not None

    def do_GET(self):
        # Logout: clear server-side session and the cookie, then redirect
        if self.path == '/logout':
            cookie_header = self.headers.get('Cookie')
            if cookie_header:
                cookie = http.cookies.SimpleCookie(cookie_header)
                if 'session_id' in cookie:
                    SESSIONS.pop(cookie['session_id'].value, None)
            self.send_response(302)
            self.send_header('Set-Cookie', 'session_id=; HttpOnly; Path=/; Max-Age=0')
            self.send_header('Location', '/login.html')
            self.end_headers()
            return

        if not self.check_auth():
            self.send_response(302)
            self.send_header('Location', '/login.html')
            self.end_headers()
            return

        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path in ['/', '/index.html'] and not parsed_path.query:
            self.send_response(302)
            self.send_header('Location', '/select.html')
            self.end_headers()
            return

        # Render select.html with tenant-specific cards
        if parsed_path.path == '/select.html':
            tenant = self.session_tenant() or "zoominfo"
            template_path = os.path.join(os.path.dirname(__file__), 'select.html')
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template = f.read()
                rendered = template.replace('<!--COURSES-->', render_cards(tenant))
                body = rendered.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except OSError as e:
                self.send_error(500, f"Failed to render select.html: {e}")
                return

        super().do_GET()

    def do_POST(self):
        if self.path == '/login':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            parsed_data = urllib.parse.parse_qs(post_data)

            username = parsed_data.get('username', [''])[0]
            password = parsed_data.get('password', [''])[0]

            tenant = None
            if username == USER1_NAME and password == USER1_PASS:
                tenant = USER_TENANTS[USER1_NAME]
            elif username == USER2_NAME and password == USER2_PASS:
                tenant = USER_TENANTS[USER2_NAME]
            elif username == USER3_NAME and password == USER3_PASS:
                tenant = USER_TENANTS[USER3_NAME]

            if tenant:
                session_id = os.urandom(16).hex()
                SESSIONS[session_id] = tenant
                self.send_response(302)
                self.send_header('Set-Cookie', f'session_id={session_id}; HttpOnly; Path=/')
                self.send_header('Location', '/select.html')
                self.end_headers()
            else:
                self.send_response(302)
                self.send_header('Location', '/login.html?error=1')
                self.end_headers()
        else:
            self.send_error(404, "Not Found")

# Prevent port conflicts by allowing reuse
http.server.ThreadingHTTPServer.allow_reuse_address = True

PORT = int(os.environ.get("PORT", 8080))
Handler = AuthHandler

try:
    with http.server.ThreadingHTTPServer(("", PORT), Handler) as httpd:
        print(f"Secure server listening at http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\nShutting down server.")