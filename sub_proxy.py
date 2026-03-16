from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request

class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        target_url = "https://key.f0rtuna.fast/cMHsUEBuHBkNetLv"
        req = urllib.request.Request(target_url)
        req.add_header('x-hwid', 'my-v2raya-bot')
        
        try:
            with urllib.request.urlopen(req) as response:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(response.read())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8000), ProxyHandler)
    print("Sub-proxy running on port 8000...")
    server.serve_forever()
