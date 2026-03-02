import http.server
import socketserver
import urllib.parse
import os
import http.cookies

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
USER1_NAME = ENV.get("USER1_NAME") or os.environ.get("USER1_NAME", "autonomous")
USER1_PASS = ENV.get("USER1_PASS") or os.environ.get("USER1_PASS", "architect123")
USER2_NAME = ENV.get("USER2_NAME") or os.environ.get("USER2_NAME", "kinesthetic")
USER2_PASS = ENV.get("USER2_PASS") or os.environ.get("USER2_PASS", "disengaged123")

# Super simple session tracking (in memory)
SESSIONS = set()

class AuthHandler(http.server.SimpleHTTPRequestHandler):
    def check_auth(self):
        if DEV_MODE:
            return True

        # Allow unauthorized access to resources needed by the login page
        if self.path in ['/login.html', '/assets/logo.png', '/login'] or self.path.startswith('/styles.css'):
            return True

        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            cookie = http.cookies.SimpleCookie(cookie_header)
            if 'session_id' in cookie and cookie['session_id'].value in SESSIONS:
                return True
        return False

    def do_GET(self):
        if not self.check_auth():
            self.send_response(302)
            self.send_header('Location', '/login.html')
            self.end_headers()
            return
            
        # Parse the URL to see if it's the root path with NO persona selected
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path in ['/', '/index.html'] and not parsed_path.query:
            self.send_response(302)
            self.send_header('Location', '/select.html')
            self.end_headers()
            return

        super().do_GET()

    def do_POST(self):
        if self.path == '/login':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            parsed_data = urllib.parse.parse_qs(post_data)
            
            username = parsed_data.get('username', [''])[0]
            password = parsed_data.get('password', [''])[0]
            
            is_valid = False
            if username == USER1_NAME and password == USER1_PASS:
                is_valid = True
            elif username == USER2_NAME and password == USER2_PASS:
                is_valid = True
                
            if is_valid:
                session_id = os.urandom(16).hex()
                SESSIONS.add(session_id)
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
socketserver.TCPServer.allow_reuse_address = True

PORT = int(os.environ.get("PORT", 8080))
Handler = AuthHandler

try:
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Secure server listening at http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\nShutting down server.")
