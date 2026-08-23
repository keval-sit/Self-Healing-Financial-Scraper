import http.server
import json
import threading
from pathlib import Path
import src.config as config

current_version = "v1"

class MockServerHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global current_version
        
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            content = get_page_content()
            self.wfile.write(content.encode('utf-8'))
            return
            
        if self.path == '/switch/v1':
            switch_version("v1")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"version": "v1", "status": "switched"}).encode('utf-8'))
            return
            
        if self.path == '/switch/v2':
            switch_version("v2")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"version": "v2", "status": "switched"}).encode('utf-8'))
            return
            
        if self.path == '/status':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"version": current_version}).encode('utf-8'))
            return
            
        self.send_response(404)
        self.end_headers()

def start_server():
    server = http.server.ThreadingHTTPServer(('', config.MOCK_SERVER_PORT), MockServerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread

def switch_version(version):
    global current_version
    if version in ["v1", "v2"]:
        current_version = version

def get_current_version():
    global current_version
    return current_version

def get_page_content(version=None):
    if version is None:
        version = current_version
    file_path = config.MOCK_SITE_DIR / f"{version}.html"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>404 Not Found</h1>"
