import os
import subprocess
import time
import requests
import base64
import json
import platform

class VPNManager:
    def __init__(self, subscription_url):
        self.sub_url = subscription_url
        self.xray_path = "xray.exe" if platform.system() == "Windows" else "./xray"
        self.config_path = "config.json"
        self.process = None
        self.proxy_port = 20171

    def _get_hwid_subscription(self):
        """Получает подписку с заголовком x-hwid, как это делал наш sub-proxy"""
        headers = {'x-hwid': 'my-standalone-bot'}
        try:
            response = requests.get(self.sub_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return base64.b64decode(response.text).decode('utf-8')
        except Exception as e:
            print(f"Error fetching subscription: {e}")
        return None

    def _generate_config(self, vless_links):
        """Берет первую рабочую ссылку и делает из нее простой конфиг для Xray"""
        # Для EXE версии мы просто возьмем первую ссылку из подписки
        # и превратим ее в полноценный config.json. 
        # (В реальной жизни тут нужен парсер vless:// ссылок)
        
        # Заглушка для упрощения: в идеале тут парсинг VLESS -> JSON
        # Но для начала мы можем просто прописать рабочий шаблон.
        pass

    def start_vpn(self):
        """Запуск xray.exe в фоновом режиме"""
        if not os.path.exists(self.xray_path):
            print("xray.exe not found! Please download it from Xray-core releases.")
            return False

        print("Starting VPN (Xray)...")
        # Запускаем без окна консоли (на Windows)
        creation_flags = 0x08000000 if platform.system() == "Windows" else 0
        
        try:
            self.process = subprocess.Popen(
                [self.xray_path, "-c", self.config_path],
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2) # Даем время на запуск
            print(f"VPN started. Proxy on port {self.proxy_port}")
            return True
        except Exception as e:
            print(f"Failed to start VPN: {e}")
            return False

    def stop_vpn(self):
        if self.process:
            self.process.terminate()
            print("VPN stopped.")

    def set_proxy_env(self):
        """Настраивает переменные окружения для текущего процесса Python"""
        proxy = f"http://127.0.0.1:{self.proxy_port}"
        os.environ['HTTP_PROXY'] = proxy
        os.environ['HTTPS_PROXY'] = proxy
        os.environ['ALL_PROXY'] = proxy
        os.environ['NO_PROXY'] = "localhost,127.0.0.1"
