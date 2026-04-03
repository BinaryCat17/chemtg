import os
from dotenv import load_dotenv
load_dotenv(".env", override=True)
import standalone_launcher as sl

links = []
url = os.getenv("VPN_SUBSCRIPTION_URL")
import requests, base64
from urllib.parse import unquote
r = requests.get(url, headers={'User-Agent': 'v2rayN/6.33'})
content = r.text.strip()
try:
    padded = content + "=" * ((4 - len(content) % 4) % 4)
    decoded_body = base64.b64decode(padded).decode('utf-8')
except:
    decoded_body = content
    
for line in decoded_body.splitlines():
    line = line.strip()
    if not line: continue
    if line.startswith("vless://"):
        links.append(line)
    else:
        try:
            padded_line = line + "=" * ((4 - len(line) % 4) % 4)
            dec = base64.b64decode(padded_line).decode('utf-8').strip()
            if dec.startswith("vless://"):
                links.append(dec)
        except:
            pass

print(f"Total links: {len(links)}")
import subprocess, time
for i, l in enumerate(links):
    print(f"--- Testing {i}: {unquote(l.split('#')[-1])}")
    p = sl.parse_vless(l)
    if not p: continue
    if sl.generate_xray_config(p):
        xray = subprocess.Popen(["bin/xray", "-c", "data/vpn/config.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        if sl.test_proxy():
            print(f"!!! SUCCESS with link {i} !!!")
            xray.terminate()
            break
        xray.terminate()
