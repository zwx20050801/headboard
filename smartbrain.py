import cv2
import mediapipe as mp
import math
import requests
import threading
import time
import json
import os
import http.server
import socketserver
import datetime
from openai import OpenAI

# ================= 1. 核心配置区 =================
CAM_URL = "http://192.168.43.17:81/stream"   
RADAR_URL = "http://192.168.43.242/radar"     
LED_URL = "http://192.168.43.242/led"         
AUDIO_URL = "http://192.168.43.242/play"  
PC_IP = "192.168.43.130"                  

QWEN_API_KEY = "sk-c192023aee08462592957dd13077fa26"          

client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
# =================================================

# --- 音频服务器 ---
def start_audio_server():
    os.chdir(os.path.dirname(os.path.abspath(__file__))) 
    Handler = http.server.SimpleHTTPRequestHandler
    with http.server.ThreadingHTTPServer(("", 8080), Handler) as httpd:
        print(f"🔊 电脑音频服务器（多线程版）已启动: http://{PC_IP}:8080")
        httpd.serve_forever()
threading.Thread(target=start_audio_server, daemon=True).start()

# --- 全局变量 ---
radar_data = {"presence": False, "moving_dist": 0, "moving_energy": 0, "stationary_dist": 0, "stationary_energy": 0}
eye_status_text = "AWAKE"
manual_override = False 

llm_decision = {
    "status": "等待数据...",
    "action": "无",
    "speech": "系统已启动，正在观察..."
}

# --- 雷达拉取 ---
def fetch_radar():
    global radar_data
    while True:
        try:
            res = requests.get(RADAR_URL, timeout=5)
            if res.status_code == 200:
                radar_data = res.json()
        except:
            pass
        time.sleep(0.1)
threading.Thread(target=fetch_radar, daemon=True).start()


# ====== 🌟 核心控制中心 ======
def execute_hardware_command(speech, led_mode):
    if led_mode and led_mode != "off":
        try:
            requests.get(f"{LED_URL}?mode={led_mode}", timeout=3.0)
            print(f"🌟 [硬件响应] 成功切换流体光效 -> {led_mode}")
        except Exception as e:
            print(f"❌ [硬件报错] 无法控制灯条: {e}")

    speech_clean = speech.replace('"', '').replace("'", "").strip()
    if speech_clean and speech_clean != "无" and speech_clean != "N/A":
        print(f"🎙️ [正在生成语音]: {speech_clean}")
        filename = f"speech_{int(time.time())}.mp3"
        os.system(f'edge-tts --voice zh-CN-XiaoxiaoNeural --text "{speech_clean}" --write-media {filename}')
        audio_url_for_esp32 = f"http://{PC_IP}:8080/{filename}"
        print(f"🚀 [正在隔空推送]...")
        try:
            requests.get(f"{AUDIO_URL}?url={audio_url_for_esp32}", timeout=3.0)
            print(f"✅ [推送成功，音箱即将发声]")
        except Exception as e:
            print(f"❌ [音频推送失败]: {e}")
# ===============================================

# --- 大模型思考引擎 ---
def llm_thinker():
    global llm_decision, radar_data, eye_status_text, manual_override
    last_status = "系统刚启动"
    
    # 🚨 核心修复：更新大模型的“光效词典”，让它必须使用这 5 个和 ESP32 完全一致的口令！
    system_prompt = """
    你是一个极其智能、富有同理心的床头管家。
    你的任务是根据用户的【传感器数据】和【时间】，推断用户的状态，并调用【流体光效模式】。

    【流体光效库】（请严格从中挑选）：
    1. "breathe_orange"：篝火呼吸。适合准备入睡时（闭眼，运动极低）。
    2. "breathe_blue"：深海律动。适合焦虑/失眠翻身时（闭眼，运动量高）。
    3. "warm_fade_in"：晨曦渐亮。适合即将起床前的柔和唤醒铺垫。
    4. "solid_white"：固定白光。适合到了时间强力唤醒，或正常清醒活动（睁眼有动作）。
    5. "off"：优雅渐隐。适合不在床上（无人检测到）时关闭。

    规则：如果状态没变，speech 必须输出 "无"。
    请严格以 JSON 格式输出：
    {"status": "...", "action": "...", "speech": "...", "led_mode": "必须只能是 breathe_orange, breathe_blue, warm_fade_in, solid_white, off 之一"}
    """
    
    while True:
        time.sleep(10)
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        current_context = f"时间：{current_time}\n上次状态：{last_status}\n- 眼睛：{eye_status_text}\n- 有人：{radar_data['presence']}\n- 运动：{radar_data['moving_energy']}\n- 静止：{radar_data['stationary_energy']}"
        
        try:
            response = client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": current_context}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            result_str = response.choices[0].message.content
            decision = json.loads(result_str)
            last_status = decision.get('status', '未知')
            
            if not manual_override:
                llm_decision = decision 
                print("[AI 自由决策] ->", llm_decision)
                execute_hardware_command(llm_decision.get('speech', '无'), llm_decision.get('led_mode', 'off'))
            else:
                print("⏸️ [AI 思考完毕] 但当前处于剧本模式，已拦截 AI 的物理控制权。")
                
        except Exception as e:
            print("[AI 思考受阻]:", e)

threading.Thread(target=llm_thinker, daemon=True).start()
print("通义千问思考引擎已启动...")


# ====== 🎬 剧本导演模式 ======
def play_scenario(scene_num):
    global manual_override, llm_decision
    manual_override = True 
    
    if scene_num == 1:
        llm_decision['status'] = "【剧本】睡前对齐"
        llm_decision['action'] = "读取日程，开启助眠"
        llm_decision['speech'] = "检测到您明天有重要答辩，将开启强力唤醒模式。已为您开启助眠呼吸光，晚安。"
        execute_hardware_command(llm_decision['speech'], "breathe_orange")
        
    elif scene_num == 2:
        llm_decision['status'] = "【剧本】清晨 7:45"
        llm_decision['action'] = "唤醒铺垫，暖光渐亮"
        llm_decision['speech'] = "答辩日早晨好，正在为您模拟晨曦渐亮。"
        execute_hardware_command(llm_decision['speech'], "warm_fade_in")
        
    elif scene_num == 3:
        llm_decision['status'] = "【剧本】清晨 8:00"
        llm_decision['action'] = "强力叫醒，固定白光"
        llm_decision['speech'] = "早上 8 点整！请立刻起床准备答辩，今天你是最棒的！"
        execute_hardware_command(llm_decision['speech'], "solid_white")
        
    elif scene_num == 0:
        manual_override = False 
        llm_decision['status'] = "系统正常运作"
        llm_decision['action'] = "已恢复 AI 自动接管"
        llm_decision['speech'] = "无"
        print("▶️ [模式切换] 已恢复 AI 自由接管模式。")

# --- 退出处理 ---
def turn_off_leds_safely():
    print("\n🛑 系统准备退出，正在向硬件发送熄灯指令...")
    try: requests.get(f"{LED_URL}?mode=off", timeout=2.0)
    except: pass

# --- 视觉主循环 ---
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

def get_distance(p1, p2, width, height):
    return math.hypot(int(p2.x * width) - int(p1.x * width), int(p2.y * height) - int(p1.y * height))

cap = cv2.VideoCapture(CAM_URL)

try:
    with mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5) as face_mesh:
        while cap.isOpened():
            success, image = cap.read()
            if not success: continue

            h, w, _ = image.shape
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(image_rgb)

            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    custom_style = mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=0)
                    mp_drawing.draw_landmarks(
                        image=image, 
                        landmark_list=face_landmarks, 
                        connections=mp_face_mesh.FACEMESH_TESSELATION, 
                        landmark_drawing_spec=None, 
                        connection_drawing_spec=custom_style 
                    )
                    
                    eye_distance = get_distance(face_landmarks.landmark[159], face_landmarks.landmark[145], w, h)
                    eye_status_text = "SLEEPING (闭眼)" if eye_distance < 6.0 else "AWAKE (睁眼)"

            overlay = image.copy()
            cv2.rectangle(overlay, (0, h - 120), (w, h), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.7, image, 0.3, 0, image)
            
            mode_text = "[Director Mode]" if manual_override else "[Auto AI Mode]"
            cv2.putText(image, mode_text, (w - 180, h - 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255) if manual_override else (0, 255, 0), 2)
            
            cv2.putText(image, f"Status: {llm_decision.get('status', 'N/A')}", (20, h - 85), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(image, f"Action: {llm_decision.get('action', 'N/A')}", (20, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(image, f"Speech: {llm_decision.get('speech', 'N/A')}", (20, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 200), 2)

            cv2.imshow('Ultimate AI Brain Dashboard', image)

            key = cv2.waitKey(5) & 0xFF
            if key == 27: break
            elif key == ord('1'): threading.Thread(target=play_scenario, args=(1,)).start()
            elif key == ord('2'): threading.Thread(target=play_scenario, args=(2,)).start()
            elif key == ord('3'): threading.Thread(target=play_scenario, args=(3,)).start()
            elif key == ord('0'): threading.Thread(target=play_scenario, args=(0,)).start()

except KeyboardInterrupt: print("\n⚠️ 检测到手动中断...")
finally:
    turn_off_leds_safely()
    cap.release()
    cv2.destroyAllWindows()