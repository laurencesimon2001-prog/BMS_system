import threading

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from db import query_db, execute_db
import subprocess, platform, os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import time
import requests  
from dotenv import load_dotenv
import nmap

# --- Load Environment Variables ---
env_path = os.path.join(os.path.dirname(__file__), 'tg.env')
load_dotenv(env_path)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "lucifer secret key 123")

UPLOAD_FOLDER = 'static/uploads/maps'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Telegram Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RAW_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

try:
    TELEGRAM_CHAT_ID = int(RAW_CHAT_ID) if RAW_CHAT_ID else None
except (ValueError, TypeError):
    TELEGRAM_CHAT_ID = RAW_CHAT_ID

# --- DEBUG PRINT (Terminal မှာ စစ်ဖို့) ---
print(f"DEBUG: Token is {TELEGRAM_TOKEN}")
print(f"DEBUG: Chat ID is {TELEGRAM_CHAT_ID} (Type: {type(TELEGRAM_CHAT_ID)})")

last_status_cache = {}

def send_telegram_alert(device_id, ip, status):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Configuration Error: Missing Token or Chat ID")
        return

    # Emoji and status text logic
    emoji = "🟢" if status == "Online" else "🔴"
    status_text = "BACK ONLINE" if status == "Online" else "OFFLINE"
    
    # Message formatting with HTML support
    msg = (
        f"{emoji} <b>SBMS Monitoring Alert</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>Device ID:</b> {device_id}\n"
        f"<b>IP Address:</b> {ip}\n"
        f"<b>Status:</b> <code>{status_text}</code>\n"
        f"<b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━"
    )
    
    # Sending request to Telegram API
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(
            url, 
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, 
            timeout=5
        )
        if response.status_code != 200:
            print(f"Telegram API Error: {response.text}")
            
    except Exception as e:
        print(f"Telegram Connection Error: {e}")

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({"success": False, "error": "Unauthorized! Admin access only."}), 403
        return f(*args, **kwargs)
    return decorated_function

def get_ping_status(ip):
    if not ip: return "Offline"
    ip = ip.strip()
    try:
        current_os = platform.system().lower()
        if current_os == "windows":
            cmd = ['ping', '-n', '1', '-w', '1000', ip]
        else:
            # ဒီနေရာမှာ 'ping' အစား '/usr/bin/ping' (Full Path) ကို သုံးရပါမယ်
            cmd = ['/usr/bin/ping', '-c', '1', '-W', '1', ip]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return "Online" if result.returncode == 0 else "Offline"
    except Exception as e:
        print(f"Ping Error for {ip}: {e}")
        return "Offline"
    
def check_and_update(dev):
    """Device တစ်ခုချင်းစီကို စစ်ဆေးပြီး လိုအပ်ရင် Update လုပ်ပေးမယ့် အလုပ်သမားလေး"""
    try:
        current_status = get_ping_status(dev['ip_address'])
        old_status = dev['last_status'] if dev['last_status'] else "Offline"
        
        if old_status != current_status:
            dev_id_str = str(dev['id'])
            # Cache ထဲမှာ အခြေအနေ အတူတူပဲ ရှိနေရင် ထပ်မပို့အောင် စစ်တယ်
            if last_status_cache.get(dev_id_str) != current_status:
                # Telegram Alert ကို thread နဲ့ ပို့မယ်
                threading.Thread(
                    target=send_telegram_alert, 
                    args=(dev['id'], dev['ip_address'], current_status), 
                    daemon=True
                ).start()
                last_status_cache[dev_id_str] = current_status
            
            # Database Update လုပ်တယ်
            execute_db("UPDATE devices SET last_status=%s, updated_at=NOW() WHERE id=%s", (current_status, dev['id']))
            execute_db("INSERT INTO device_logs (device_id, device_name, status) VALUES (%s, %s, %s)", (dev['id'], dev['device_name'], current_status))
    except Exception as e:
        print(f"Error checking device {dev['ip_address']}: {e}")

def background_monitor():
    """အလုပ်သမား ၅၀ ကို တစ်ပြိုင်တည်း ခိုင်းပြီး အမြန်စစ်မယ့် Monitor"""
    print("[System] Parallel Monitor Started - 300+ Devices Optimized Mode")
    while True:
        try:
            # Database ကနေ device စာရင်း ယူတယ်
            devices = query_db("SELECT id, device_name, ip_address, last_status FROM devices")
            if devices:
                # အလုပ်သမား (Threads) ၅၀ နဲ့ တစ်ပြိုင်တည်း ပစ်စစ်မယ်
                with ThreadPoolExecutor(max_workers=50) as executor:
                    executor.map(check_and_update, devices)
        except Exception as e:
            print(f"Monitor Loop Error: {e}")
        
        # တစ်ပတ်ပြီးတိုင်း ၅ စက္ကန့် သို့မဟုတ် ၁၀ စက္ကန့် နားမယ်
        time.sleep(5)

def get_device_counts(dtype):
    total = query_db("SELECT COUNT(*) as count FROM devices WHERE LOWER(TRIM(device_type)) LIKE %s", (f"%{dtype.lower()}%",), one=True)
    online = query_db("SELECT COUNT(*) as count FROM devices WHERE LOWER(TRIM(device_type)) LIKE %s AND last_status='Online'", (f"%{dtype.lower()}%",), one=True)
    t = total['count'] if total else 0
    o = online['count'] if online else 0
    return f"{o}/{t} Online"

# API Routes

@app.route('/api/stats')
@login_required
def get_stats():
    try:
        # ၁။ အခြေခံအချက်အလက်များကို Query လုပ်ခြင်း
        total_users = query_db("SELECT COUNT(*) as count FROM users", one=True)
        active_tasks = query_db("SELECT COUNT(*) as count FROM tasks WHERE status!='Done'", one=True)
        
        # စက်ပစ္စည်းများ၏ Status ကို တွက်ချက်ခြင်း
        internet = get_ping_status("8.8.8.8")
        router = get_device_counts('router')
        cctv = get_device_counts('cctv')
        
        # POS အတွက် သီးသန့် Query
        pos_data = query_db("SELECT COUNT(*) as count FROM devices WHERE LOWER(device_type) LIKE '%pos%' AND last_status='Online'", one=True)
        pos_total = query_db("SELECT COUNT(*) as count FROM devices WHERE LOWER(device_type) LIKE '%pos%'", one=True)

        # ၂။ Chart အတွက် Device အားလုံးကို ခြုံငုံပြီး တွက်ချက်ခြင်း (Wireless + Router အကုန်ပါတယ်)
        # ဒီအပိုင်းကို Try block ထဲမှာ အမှန်ကန်ဆုံး Indent လုပ်ထားတယ်
        t_on = query_db("SELECT COUNT(*) as count FROM devices WHERE last_status = 'Online'", one=True)
        t_all = query_db("SELECT COUNT(*) as count FROM devices", one=True)
        
        on_count = t_on['count'] if t_on else 0
        all_count = t_all['count'] if t_all else 0

        # ၃။ အချက်အလက်အားလုံးကို JSON ပုံစံဖြင့် ပြန်ပို့ခြင်း
        return jsonify({
            "total_users": total_users['count'] if total_users else 0,
            "active_tasks": active_tasks['count'] if active_tasks else 0,
            "internet": internet,
            "router": router,
            "cctv": cctv,
            "pos": f"{pos_data['count']}/{pos_total['count']} Online" if pos_total else "0/0 Online",
            # Chart ဆွဲရန်အတွက် Online ၅ ခုလုံး ပါမည့် Raw Data
            "total_online_raw": on_count,
            "total_offline_raw": all_count - on_count
        })

    except Exception as e:
        # Error တက်လျှင် Terminal တွင် ပြသရန်
        print(f"Error in get_stats: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/scan-network', methods=['POST'])
@login_required
@admin_required
def scan_network_api():
    try:
        # Initialize PortScanner
        nm = nmap.PortScanner()
        
        target_networks = "192.168.90.0/24 192.168.100.0/24"
        
        scan_args = '-sn -PE -T4'
        
        nm.scan(hosts=target_networks, arguments=scan_args)
        
        
        existing_devices = query_db("SELECT ip_address FROM devices")
        existing_ips = [d['ip_address'] for d in existing_devices]
        
        new_devices_count = 0
        
        for host in nm.all_hosts():
            
            if nm[host].state() == 'up':
                if host not in existing_ips:
                
                    hostname = nm[host].hostname() or f"New Device ({host})"
                    
                    execute_db(
                        "INSERT INTO devices (device_name, ip_address, device_type, last_status, updated_at) VALUES (%s, %s, %s, %s, NOW())",
                        (hostname, host, 'router', 'Online')
                    )
                    new_devices_count += 1
                
        return jsonify({
            "status": "success",
            "success": True, 
            "message": f"Scan complete. Found {new_devices_count} new devices."
        }), 200
        
    except nmap.PortScannerError as e:
        return jsonify({"status": "error", "message": f"Nmap Error: {str(e)}"}), 500
    except Exception as e:
    
        print(f"DEBUG ERROR: {str(e)}")
        return jsonify({"status": "error", "message": f"System Error: {str(e)}"}), 500
    
@app.route('/api/logs')
@login_required
def get_logs():
    logs = query_db("SELECT * FROM device_logs ORDER BY timestamp DESC LIMIT 20")
    return jsonify([dict(l) for l in logs]) if logs else jsonify([])

@app.route('/api/devices')
@login_required
def get_devices():
    return jsonify(query_db("SELECT * FROM devices ORDER BY id DESC"))

@app.route('/api/agent/report', methods=['POST'])
def agent_report():
    data = request.get_json()
    if not data: return jsonify({"error": "No data"}), 400
    device_id, status, ip = str(data.get('device_id')), data.get('status'), data.get('ip', 'Unknown IP')
    
    if device_id and status:
        if last_status_cache.get(device_id) != status:
            send_telegram_alert(device_id, ip, status)
            last_status_cache[device_id] = status
            dev_info = query_db("SELECT device_name FROM devices WHERE id=%s", (device_id,), one=True)
            execute_db("INSERT INTO device_logs (device_id, device_name, status) VALUES (%s, %s, %s)", (device_id, dev_info['device_name'] if dev_info else "Agent Device", status))
        execute_db("UPDATE devices SET last_status=%s, updated_at=NOW() WHERE id=%s", (status, device_id))
        return jsonify({"success": True}), 200
    return jsonify({"error": "Invalid fields"}), 400

@app.route('/api/devices/add', methods=['POST'])
@login_required
@admin_required
def add_device_api():
    data = request.get_json() or request.form
    name, ip, dtype = data.get('name'), data.get('ip'), data.get('type')
    if not name or not ip: return jsonify({"error": "Missing data"}), 400
    execute_db("INSERT INTO devices (device_name, ip_address, device_type, last_status, updated_at) VALUES (%s, %s, %s, 'Offline', NOW())", (name, ip, dtype))
    return jsonify({"success": True})

@app.route('/api/devices/delete/<int:id>', methods=['DELETE'])
@login_required
@admin_required
def delete_device_api(id):
    execute_db("DELETE FROM devices WHERE id=%s", (id,))
    return jsonify({"success": True})

@app.route('/api/upload_map', methods=['POST'])
@login_required
@admin_required
def upload_map():
    if 'map_file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['map_file']
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({"success": True, "map_url": f"/static/uploads/maps/{filename}"})
    return jsonify({"error": "Failed"}), 400

@app.route('/api/devices/set_position', methods=['POST'])
@login_required
@admin_required
def set_position():
    data = request.get_json()
    execute_db("UPDATE devices SET ps_x=%s, ps_y=%s WHERE id=%s", (float(data.get('ps_x')), float(data.get('ps_y')), int(data.get('id'))))
    return jsonify({"success": True})

@app.route('/api/devices/unpositioned')
@login_required
def get_unpositioned_devices():
    return jsonify(query_db("SELECT id, device_name FROM devices WHERE ps_x IS NULL"))

# Page Routes 
@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = query_db("SELECT * FROM users WHERE username = %s", (request.form.get('username'),), one=True)
        if user and check_password_hash(user['password'], request.form.get('password')):
            session.update({'user_id': user['id'], 'username': user['username'], 'role': user['role']})
            return redirect(url_for('dashboard'))
        flash("Invalid credentials!")
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    total_u = query_db("SELECT COUNT(*) as count FROM users", one=True)
    active_t = query_db("SELECT COUNT(*) as count FROM tasks WHERE status!='Done'", one=True)
    wireless_list = query_db("SELECT device_name, last_status FROM devices WHERE LOWER(device_type) LIKE '%wifi%'")
    return render_template('dashboard.html', 
        user=session.get('username'), role=session.get('role'), 
        total_users=total_u['count'] if total_u else 0, 
        active_tasks=active_t['count'] if active_t else 0, 
        net_status=get_ping_status("8.8.8.8"), 
        router_status=get_device_counts('router'), 
        cctv_status=get_device_counts('cctv'), 
        pos_status=get_device_counts('pos'),
        wireless_list=wireless_list)

@app.route('/monitoring', methods=['GET', 'POST'])
@login_required
def monitoring():
    if request.method == 'POST' and session.get('role') == 'admin':
        name, ip, dtype = request.form.get('device_name'), request.form.get('ip_address'), request.form.get('device_type')
        if name and ip:
            execute_db("INSERT INTO devices (device_name, ip_address, device_type, last_status, updated_at) VALUES (%s, %s, %s, 'Offline', NOW())", (name, ip, dtype))
            flash("Device added")
        return redirect(url_for('monitoring'))
    return render_template('monitoring.html', devices=query_db("SELECT * FROM devices ORDER BY id DESC"), role=session.get('role'))

@app.route('/delete_device/<int:id>')
@login_required
@admin_required
def delete_device_page(id):
    execute_db("DELETE FROM devices WHERE id=%s", (id,))
    flash("Device removed")
    return redirect(url_for('monitoring'))

@app.route('/edit_device/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_device(id):
    name, ip, dtype = request.form.get('device_name'), request.form.get('ip_address'), request.form.get('device_type')
    execute_db("UPDATE devices SET device_name=%s, ip_address=%s, device_type=%s, updated_at=NOW() WHERE id=%s", (name, ip, dtype, id))
    flash("Device updated")
    return redirect(url_for('monitoring'))

@app.route('/tasks', methods=['GET', 'POST'])
@login_required
def manage_tasks():
    if request.method == 'POST' and session.get('role') == 'admin':
        execute_db("INSERT INTO tasks (title, assigned_to, priority, status, due_date) VALUES (%s, %s, %s, %s, %s)", (request.form.get('title'), int(request.form.get('assigned_to')), request.form.get('priority'), 'Pending', request.form.get('due_date') or None))
        flash("Task added")
    staff = query_db("SELECT id, username FROM users")
    tasks = query_db("SELECT t.*, u.username as staff_name FROM tasks t LEFT JOIN users u ON t.assigned_to = u.id ORDER BY t.id DESC")
    return render_template('tasks.html', tasks=tasks, staff=staff, role=session.get('role'))

@app.route('/update_task/<int:id>/<string:status>')
@login_required
def update_task_status(id, status):
    execute_db("UPDATE tasks SET status=%s WHERE id=%s", (status, id))
    flash(f"Task status updated to {status}")
    return redirect(url_for('manage_tasks'))

@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    if request.method == 'POST':
        execute_db("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", (request.form.get('username'), generate_password_hash(request.form.get('password')), request.form.get('role')))
    return render_template('user.html', users=query_db("SELECT * FROM users"))

@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=background_monitor, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=5000)