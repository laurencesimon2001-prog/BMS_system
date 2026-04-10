import requests
import time
import socket
import os

SERVER_URL = "http://192.168.90.50:5000/api/agent/report"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def send_heartbeat():
    DEVICE_ID = 28 
    
    print(f"Agent Started for Device ID: {DEVICE_ID}")
    
    while True:
        try:
            data = {
                "device_id": DEVICE_ID,
                "status": "Online",
                "ip": get_ip()
            }
            requests.post(SERVER_URL, json=data, timeout=5)
        except Exception as e:
            print(f"Server Connection Error: {e}")
        
        time.sleep(30) 

if __name__ == "__main__":
    send_heartbeat()