import cv2
import numpy as np
# from pythonosc import udp_client # OSC 통신을 위해 필요했으나 현재는 사운드 자체 생성을 위해 주석 처리함
import time
import math
import sounddevice as sd
import queue
import threading
import collections
import random
import subprocess
import platform

# --- 1. 설정 (Configuration) ---
CAMERA_INDEX = 0
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080

# --- OSC 설정 (현재 사용 안함 - 주석 처리) ---
# OSC_IP = "192.168.0.2"
# OSC_PORT = 8000
# OSC_ADDRESS = "/shadow_data"

# --- 시각화 옵션 ---
# 뷰 모드: 1 = Minimal Debug Visual, 2 = Binary Mask
current_view_mode = 1

# 'h' 키로 토글할 정보 텍스트 표시 여부
show_info_text = True 

# 'b' 버튼 플래시 설정
white_flash_active = False
white_flash_alpha = 0.0
FLASH_DURATION = 0.3
FADE_OUT_START_ALPHA = 1.0
flash_start_time = 0

# --- 큐브 애니메이션 설정 ---
NUM_CUBES = 3
CUBE_COLOR = (255, 255, 255)
CUBE_ANIM_DURATION = 0.5
CUBE_DELAY_PER_CUBE = 0.1

cube_states = []
for _ in range(NUM_CUBES):
    cube_states.append({
        'active': False,
        'start_time': 0,
        'alpha': 0.0,
        'phase': 'idle'
    })

# --- 에코 (잔상) 효과 설정 ---
echo_active = False
ECHO_FRAMES_TO_STORE = 15
ECHO_ALPHA_DECAY_RATE = 0.05
echo_frame_buffer = collections.deque(maxlen=ECHO_FRAMES_TO_STORE)

# --- 글리치 효과 설정 ---
glitch_active = False
GLITCH_STRENGTH = 20
GLITCH_NUM_EFFECTS = 5

# --- 오토 파일럿 설정 ---
auto_pilot_active = True
last_beat_time = 0
beat_count = 0

# --- 오디오 설정 (Sound Engine) ---
SAMPLERATE = 44100
BLOCKSIZE = 1024 # Latency vs Stability
CHANNELS = 2 # Stereo for spatial effects

class SoundEngine:
    def __init__(self):
        self.active = True
        self.start_time = time.time()
        self.phase = 0 # 0: Data Stream, 1: Pulse/Rhythm, 2: Entropy/Noise
        
        # Tracking Data
        self.shadow_detected = False
        self.norm_dist = 0.0
        self.angle = 0.0
        self.shadow_x = 0
        self.shadow_y = 0
        self.shadow_area = 0.0 # New: Shadow size
        
        # Audio State
        self.phase_accumulator = 0.0
        self.pulse_accumulator = 0.0
        self.glitch_timer = 0.0
        self.random_seed = 0.0
        
        # Performance Config
        self.total_duration = 200.0 # 200 seconds (Extended)
        self.current_bpm = 120.0
        
        # Stream
        self.stream = sd.OutputStream(
            samplerate=SAMPLERATE,
            blocksize=BLOCKSIZE,
            channels=CHANNELS,
            callback=self.callback
        )
        self.stream.start()

    def update_tracking(self, detected, x, y, dist, angle, area):
        self.shadow_detected = detected
        self.shadow_x = x
        self.shadow_y = y
        self.norm_dist = dist
        self.angle = angle
        self.shadow_area = area

    def reset_timer(self):
        self.start_time = time.time()

    def callback(self, outdata, frames, time_info, status):
        if status:
            print(status)
        
        # Time management
        current_time = time.time()
        elapsed = current_time - self.start_time
        progress = min(1.0, elapsed / self.total_duration)
        
        # Determine Phase (Ryoji Ikeda Structure)
        # 0-33%: "Spectra" - Pure sines, high freq, data sonification
        # 33-66%: "Pulse" - Hard kicks, rhythmic clicks, radar sounds
        # 66-100%: "Matrix" - White noise, heavy glitch, intense stereo
        
        # Determine Phase (Ryoji Ikeda Structure)
        # 0-30%: "Spectra" - Pure sines, high freq, data sonification
        # 30-60%: "Pulse" - Hard kicks, rhythmic clicks, radar sounds
        # 60-85%: "Matrix" - White noise, heavy glitch, intense stereo
        # 85-100%: "Terminal" - Climax, Distortion, Feedback
        
        if progress < 0.30:
            self.phase = 0 
        elif progress < 0.60:
            self.phase = 1 
        elif progress < 0.85:
            self.phase = 2 
        else:
            self.phase = 3 # Climax 

        # Generate time array for this block
        t = (np.arange(frames) + self.phase_accumulator) / SAMPLERATE
        self.phase_accumulator += frames
        
        # Initialize output buffer
        output = np.zeros((frames, CHANNELS))
        
        # --- Sound Generation Logic (Ryoji Ikeda Style Enhanced) ---
        
        # Parameter Mapping
        # X Axis -> Stereo Panning (Left <-> Right)
        # Y Axis -> Timbre / Filter (Top: Clean, Bottom: Dirty/Noisy)
        # Distance -> Intensity / Pitch
        # Area -> Density / Volume
        
        pan = (self.shadow_x / FRAME_WIDTH) * 2.0 - 1.0 # -1.0 to 1.0
        pan = np.clip(pan, -1.0, 1.0)
        
        # Hard panning for Ikeda style (Binary stereo)
        if abs(pan) < 0.2: pan = 0.0
        elif pan > 0: pan = 0.8
        else: pan = -0.8
            
        left_gain = np.clip(1.0 - pan, 0, 1)
        right_gain = np.clip(1.0 + pan, 0, 1)
        
        y_mod = self.shadow_y / FRAME_HEIGHT # 0.0 (Top) to 1.0 (Bottom)
        
        # 1. "Spectra" - High Frequency Sine (Data Stream)
        if self.phase >= 0:
            # Base high pitch sine (Signature Ikeda sound)
            # Frequencies often used: 15kHz+, or very pure low sines
            
            # Two interacting sine waves
            f1 = 2000.0 + (1.0 - self.norm_dist) * 1000.0
            f2 = f1 + 4.0 # Beating frequency
            
            sine1 = np.sin(2 * np.pi * f1 * t)
            sine2 = np.sin(2 * np.pi * f2 * t)
            
            # Data gating (Morse code-like beeps)
            # Speed increases with Y position
            gate_speed = 10.0 + (y_mod * 40.0) 
            gate = np.where(np.sin(2 * np.pi * gate_speed * t) > 0.9, 1.0, 0.0)
            
            sig1 = (sine1 + sine2) * 0.5 * gate * 0.15
            
            if self.shadow_detected:
                output[:, 0] += sig1 * left_gain
                output[:, 1] += sig1 * right_gain
            else:
                # Idle sound: Very quiet high pitch constant
                output += np.sin(2 * np.pi * 15000 * t)[:, np.newaxis] * 0.01

        # 2. "Pulse" - Rhythmic Clicks and Bass (Heartbeat)
        if self.phase >= 1 or (self.phase == 0 and self.shadow_detected and self.norm_dist < 0.3):
            # Impulse / Click
            # Ryoji Ikeda uses very short samples (1-2ms). We simulate with filtered noise or short envelope sine.
            
            bpm = 120.0 + (progress * 60.0)
            self.current_bpm = bpm
            beat_interval = 60.0 / bpm
            
            # Simple beat generation using modulo time
            beat_trigger = np.mod(t, beat_interval)
            # Sharp decay envelope
            envelope = np.exp(-beat_trigger * 100.0) 
            
            # Carrier: Low sine for bass, Noise for click
            kick = np.sin(2 * np.pi * 60 * t) * envelope * 0.8
            click = np.random.uniform(-1, 1, frames) * envelope * 0.3
            
            sig2 = kick + click
            
            # Only play if shadow is active or in later phases
            if self.shadow_detected or self.phase >= 1:
                # In phase 1, movement affects rhythm subdivision
                if self.norm_dist < 0.5:
                    # Double time
                    beat_trigger_2 = np.mod(t, beat_interval / 2.0)
                    envelope_2 = np.exp(-beat_trigger_2 * 100.0)
                    sig2 += (np.random.uniform(-1, 1, frames) * envelope_2 * 0.2)
                
                output[:, 0] += sig2 * 0.6 # Center focused
                output[:, 1] += sig2 * 0.6

        # 3. "Matrix" - Pure Noise and Glitch (Entropy)
        if self.phase >= 2:
            # White noise bursts
            noise = np.random.uniform(-0.5, 0.5, frames)
            
            # Glitch probability increases with shadow area
            glitch_prob = 0.05 + (self.shadow_area / (FRAME_WIDTH * FRAME_HEIGHT)) * 0.5
            glitch_prob = min(glitch_prob, 0.8)
            
            # Random gating
            glitch_mask = np.random.choice([0, 1], size=frames, p=[1-glitch_prob, glitch_prob])
            
            sig3 = noise * glitch_mask * 0.4
            
            # Stereo spread based on X
            output[:, 0] += sig3 * right_gain # Invert for disorientation
            output[:, 1] += sig3 * left_gain

        # 4. "Terminal" - Climax (Distortion & Feedback)
        if self.phase == 3:
            # Intense high-pitch feedback sweep
            f_scream = 3000.0 + (np.sin(elapsed * 15.0) * 2000.0)
            scream = np.sin(2 * np.pi * f_scream * t) * 0.15
            
            # Sub-bass drone
            sub = np.sin(2 * np.pi * 45 * t) * 0.4
            
            # Add to output
            output[:, 0] += scream + sub
            output[:, 1] += scream + sub
            
            # Hard Clipping / Distortion of the entire mix
            output *= 1.5 # Boost gain
            # Clipping happens at the end (Master Limiter)

        # Master Limiter
        output = np.clip(output, -0.8, 0.8)
        
        # Write to buffer
        outdata[:] = output.astype(np.float32)

    def close(self):
        self.stream.stop()
        self.stream.close()

# --- 2. 초기화 함수 ---

def initialize_camera(index, width, height):
    """카메라를 초기화하고 설정합니다."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise IOError(f"오류: 카메라 {index}를 열 수 없습니다.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    print(f"카메라 해상도: {width}x{height}")
    return cap



def get_camera_names():
    """macOS에서 system_profiler를 사용하여 연결된 카메라 이름을 가져옵니다."""
    camera_names = []
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(['system_profiler', 'SPCameraDataType'], capture_output=True, text=True)
            output = result.stdout
            lines = output.split('\n')
            current_camera = ""
            for line in lines:
                line = line.strip()
                if line and line.endswith(":") and not line.startswith("Model ID") and not line.startswith("Unique ID"):
                    current_camera = line[:-1]
                    camera_names.append(current_camera)
        except Exception as e:
            print(f"카메라 이름 가져오기 실패: {e}")
    return camera_names

def list_available_cameras(max_cameras=5):
    """사용 가능한 카메라 인덱스를 확인하고 출력합니다."""
    print("사용 가능한 카메라 확인 중...")
    
    # 시스템에서 감지된 카메라 이름 가져오기 (참고용)
    detected_names = get_camera_names()
    if detected_names:
        print("시스템에서 감지된 카메라 목록 (순서가 인덱스와 일치하지 않을 수 있음):")
        for i, name in enumerate(detected_names):
            print(f"  - {name}")
    
    available_cameras = []
    for i in range(max_cameras):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            print(f"  [{i}] 카메라 사용 가능")
            available_cameras.append(i)
            cap.release()
    
    if not available_cameras:
        print("  사용 가능한 카메라를 찾을 수 없습니다.")
    
    return available_cameras

# def initialize_osc_client(ip, port, address):
#     """OSC 클라이언트를 초기화합니다. (현재 미사용)"""
#     try:
#         client = udp_client.SimpleUDPClient(ip, port)
#         print(f"OSC 클라이언트 초기화됨: {ip}:{port}, 주소: {address}")
#         return client
#     except Exception as e:
#         print(f"OSC 클라이언트 초기화 실패: {e}")
#         print("OSC 없이 계속 실행됩니다.")
#         return None

def setup_control_panel(width, height):
    """디버그 및 제어판 창과 트랙바를 설정합니다."""
    def on_trackbar(val):
        pass

    cv2.namedWindow('Main View', cv2.WINDOW_NORMAL) # Fullscreen support
    cv2.moveWindow('Main View', 0, 0) # 창 위치를 좌상단으로 고정
    cv2.namedWindow('Control Panel')

    max_roi_radius = min(width, height) // 2 - 10
    initial_roi_radius = max_roi_radius
    cv2.createTrackbar('ROI Radius', 'Control Panel', initial_roi_radius, max_roi_radius, on_trackbar)

    initial_threshold = 60
    cv2.createTrackbar('Threshold', 'Control Panel', initial_threshold, 255, on_trackbar)

    initial_min_area = 100
    max_min_area = width * height // 2
    cv2.createTrackbar('Min Area', 'Control Panel', initial_min_area, max_min_area, on_trackbar)

def get_trackbar_values():
    """트랙바에서 현재 값을 읽어옵니다."""
    roi_radius = cv2.getTrackbarPos('ROI Radius', 'Control Panel')
    threshold_value = cv2.getTrackbarPos('Threshold', 'Control Panel')
    min_contour_area = cv2.getTrackbarPos('Min Area', 'Control Panel')
    return max(1, roi_radius), max(1, threshold_value), max(1, min_contour_area)

# --- 3. 핵심 이미지 처리 함수 ---

def process_frame_for_shadow(frame, center_x, center_y, roi_radius, threshold_value, min_contour_area):
    """
    주어진 프레임에서 그림자를 감지하고 관련 데이터를 계산합니다.
    감지된 그림자의 중심 좌표, 정규화된 거리, 각도 및 감지 여부를 반환합니다.
    """
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, binary_frame_full = cv2.threshold(gray_frame, threshold_value, 255, cv2.THRESH_BINARY_INV)
    
    mask = np.zeros((FRAME_HEIGHT, FRAME_WIDTH), dtype=np.uint8)
    cv2.circle(mask, (center_x, center_y), roi_radius, 255, -1)
    binary_frame_masked = cv2.bitwise_and(binary_frame_full, binary_frame_full, mask=mask)
    
    contours, _ = cv2.findContours(binary_frame_masked, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    shadow_x, shadow_y = -1, -1
    normalized_distance = 0.0
    angle_degrees = 0.0
    is_shadow_detected = False
    largest_contour_found = None

    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest_contour) > min_contour_area:
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])

                if np.sqrt((cx - center_x)**2 + (cy - center_y)**2) <= roi_radius:
                    is_shadow_detected = True
                    largest_contour_found = largest_contour
                    shadow_x, shadow_y = cx, cy
                    
                    distance_from_center = np.sqrt((shadow_x - center_x)**2 + (shadow_y - center_y)**2)
                    normalized_distance = min(1.0, distance_from_center / roi_radius)
                    
                    relative_x = shadow_x - center_x
                    relative_y = center_y - shadow_y
                    angle_radians = math.atan2(relative_y, relative_x)
                    angle_degrees = (90 - math.degrees(angle_radians)) % 360
                    if angle_degrees < 0:
                        angle_degrees += 360

    return (shadow_x, shadow_y, normalized_distance, angle_degrees, is_shadow_detected), largest_contour_found, binary_frame_masked

# --- 4. 시각화 및 효과 함수 ---

def draw_base_visualization(vis_frame, center_x, center_y, roi_radius, shadow_x, shadow_y, normalized_distance, largest_contour_found, is_shadow_detected, white_color):
    """기본 ROI, 중심, 그림자 윤곽선 및 정보를 그립니다."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    font_thickness = 1

    cv2.circle(vis_frame, (center_x, center_y), roi_radius, white_color, 1)
    cv2.circle(vis_frame, (center_x, center_y), 5, white_color, -1)

    if is_shadow_detected and largest_contour_found is not None:
        cv2.drawContours(vis_frame, [largest_contour_found], -1, white_color, 2)
        cv2.circle(vis_frame, (shadow_x, shadow_y), 7, white_color, -1)
        cv2.line(vis_frame, (center_x, center_y), (shadow_x, shadow_y), white_color, 1)
        
        dist_text = f"{normalized_distance:.2f}"
        text_size = cv2.getTextSize(dist_text, font, font_scale, font_thickness)[0]
        text_x = shadow_x + 15
        text_y = shadow_y + text_size[1] // 2
        cv2.putText(vis_frame, dist_text, (text_x, text_y), font, font_scale, white_color, font_thickness)
    return vis_frame

def apply_glitch_effect(vis_frame, active, strength, num_effects):
    """프레임에 글리치 효과를 적용합니다."""
    if not active:
        return vis_frame.copy()

    temp_frame = vis_frame.copy()
    
    # 1. 세로줄 뭉개짐
    for _ in range(num_effects // 2):
        y_start = random.randint(0, FRAME_HEIGHT - strength)
        height = random.randint(5, strength * 2)
        height = min(height, FRAME_HEIGHT - y_start)
        shift_amount = random.randint(-strength, strength)
        
        if y_start + height <= FRAME_HEIGHT:
            temp_frame[y_start : y_start + height, :, :] = np.roll(
                temp_frame[y_start : y_start + height, :, :], shift_amount, axis=1
            )
    
    # 2. 색상 채널 분리
    b, g, r = cv2.split(temp_frame)
    b_shift_x = random.randint(-5, 5)
    g_shift_x = random.randint(-5, 5)
    r_shift_x = random.randint(-5, 5)
    
    b_shifted = np.roll(b, b_shift_x, axis=1)
    g_shifted = np.roll(g, g_shift_x, axis=1)
    r_shifted = np.roll(r, r_shift_x, axis=1)
    
    temp_frame = cv2.merge([b_shifted, g_shifted, r_shifted])

    # 3. 랜덤 블록 노이즈
    for _ in range(num_effects):
        block_x = random.randint(0, FRAME_WIDTH - strength)
        block_y = random.randint(0, FRAME_HEIGHT - strength)
        block_w = random.randint(5, strength)
        block_h = random.randint(5, strength)
        
        block_w = min(block_w, FRAME_WIDTH - block_x)
        block_h = min(block_h, FRAME_HEIGHT - block_y)
        
        random_color = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
        
        cv2.rectangle(temp_frame, (block_x, block_y), 
                      (block_x + block_w, block_y + block_h), random_color, -1)
    
    return temp_frame

def apply_echo_effect(vis_frame, active, frame_buffer, frames_to_store, alpha_decay_rate):
    """프레임에 에코(잔상) 효과를 적용합니다."""
    if not active:
        return vis_frame

    for i, prev_frame in enumerate(list(frame_buffer)):
        alpha = 1.0 - (i * alpha_decay_rate)
        alpha = max(0.0, min(1.0, alpha))

        if alpha > 0:
            cv2.addWeighted(prev_frame, alpha, vis_frame, 1 - alpha, 0, vis_frame)
    return vis_frame

def apply_flash_effect(vis_frame, current_time, active, start_time, duration, fade_start_alpha):
    """프레임에 흰색 플래시 효과를 적용하고 상태를 업데이트합니다."""
    global white_flash_active, white_flash_alpha, flash_start_time

    if active:
        elapsed_time = current_time - start_time
        if elapsed_time < duration:
            fade_progress = elapsed_time / duration
            white_flash_alpha = fade_start_alpha * (1.0 - fade_progress)
            white_flash_alpha = max(0.0, white_flash_alpha)
        else:
            white_flash_active = False
            white_flash_alpha = 0.0

    if white_flash_alpha > 0:
        overlay = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), 255, dtype=np.uint8)
        cv2.addWeighted(overlay, white_flash_alpha, vis_frame, 1 - white_flash_alpha, 0, vis_frame)
    return vis_frame

def update_and_draw_cubes(vis_frame, current_time):
    """큐브 애니메이션 상태를 업데이트하고 프레임에 큐브를 그립니다."""
    global cube_states
    cube_height = FRAME_HEIGHT // NUM_CUBES

    for i in range(NUM_CUBES):
        cube_state = cube_states[i]

        if cube_state['active']:
            elapsed_cube_time = current_time - cube_state['start_time']
            
            if elapsed_cube_time < CUBE_ANIM_DURATION / 2:
                cube_state['phase'] = 'fade_in'
                progress = elapsed_cube_time / (CUBE_ANIM_DURATION / 2)
                cube_state['alpha'] = progress
            elif elapsed_cube_time < CUBE_ANIM_DURATION:
                cube_state['phase'] = 'fade_out'
                progress = (elapsed_cube_time - CUBE_ANIM_DURATION / 2) / (CUBE_ANIM_DURATION / 2)
                cube_state['alpha'] = 1.0 - progress
            else:
                cube_state['active'] = False
                cube_state['alpha'] = 0.0
                cube_state['phase'] = 'idle'
        
        if cube_state['alpha'] > 0:
            y1 = i * cube_height
            y2 = (i + 1) * cube_height
            
            cube_overlay = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), CUBE_COLOR, dtype=np.uint8)
            
            cube_overlay_region = cube_overlay[y1:y2, 0:FRAME_WIDTH]
            vis_frame_region = vis_frame[y1:y2, 0:FRAME_WIDTH]
            
            cv2.addWeighted(cube_overlay_region, cube_state['alpha'], 
                            vis_frame_region, 1 - cube_state['alpha'], 0, vis_frame_region)
            
            vis_frame[y1:y2, 0:FRAME_WIDTH] = vis_frame_region
    return vis_frame

def draw_info_overlay(vis_frame, shadow_x, shadow_y, normalized_distance, angle_degrees, is_shadow_detected, fps, white_color, sound_engine):
    """디버그 정보 텍스트 오버레이를 그립니다."""
    global show_info_text

    if show_info_text:
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        font_thickness = 2
        
        status_text = "DETECTED" if is_shadow_detected else "NOT FOUND"
        
        cv2.putText(vis_frame, f'Shadow Pos: ({shadow_x},{shadow_y})', (10, 30), font, font_scale, white_color, font_thickness)
        cv2.putText(vis_frame, f'Norm Dist: {normalized_distance:.2f}', (10, 60), font, font_scale, white_color, font_thickness)
        cv2.putText(vis_frame, f'Angle: {angle_degrees:.2f} deg', (10, 90), font, font_scale, white_color, font_thickness)
        cv2.putText(vis_frame, f'Status: {status_text}', (10, 120), font, font_scale, white_color, font_thickness)
        
        # Sound Info
        elapsed = time.time() - sound_engine.start_time
        phase_names = ["Spectra (Sine)", "Pulse (Rhythm)", "Matrix (Noise)", "Terminal (Climax)"]
        phase_name = phase_names[sound_engine.phase] if sound_engine.phase < len(phase_names) else "Unknown"
        cv2.putText(vis_frame, f'Time: {elapsed:.1f}s / {sound_engine.total_duration}s', (10, 150), font, font_scale, white_color, font_thickness)
        cv2.putText(vis_frame, f'Phase: {phase_name}', (10, 180), font, font_scale, white_color, font_thickness)
        
        fps_text = f"FPS: {int(fps)}"
        cv2.putText(vis_frame, fps_text, (FRAME_WIDTH - 150, 30), font, font_scale, white_color, font_thickness)

        cv2.putText(vis_frame, f'Info text toggle: Press H', (10, FRAME_HEIGHT - 10), cv2.FONT_HERSHEY_PLAIN, 1, white_color, 1)
        cv2.putText(vis_frame, f'Fullscreen: Press F', (10, FRAME_HEIGHT - 30), cv2.FONT_HERSHEY_PLAIN, 1, white_color, 1)
        
        auto_text = "AUTO: ON" if auto_pilot_active else "AUTO: OFF"
        cv2.putText(vis_frame, f'{auto_text} (Press A)', (10, FRAME_HEIGHT - 50), cv2.FONT_HERSHEY_PLAIN, 1, white_color, 1)
    return vis_frame

def draw_view_indicator(frame):
    """현재 뷰 모드를 표시합니다."""
    global current_view_mode
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    view_text = f"View: {'[1] Visual' if current_view_mode == 1 else '[2] Binary'}"
    cv2.putText(frame, view_text, (FRAME_WIDTH - 200, FRAME_HEIGHT - 20), 
                font, 0.6, (255, 255, 255), 1)

# --- 5. 키 입력 처리 함수 ---

def handle_key_press(key, sound_engine):
    """키 입력 이벤트를 처리하고 관련 전역 상태를 업데이트합니다."""
    global show_info_text, white_flash_active, flash_start_time, echo_active, glitch_active
    global cube_states, current_view_mode, auto_pilot_active


    if key == ord('p'):  # 'p' 키로 프로그램 종료
        print("프로그램을 종료합니다.")
        return True
    elif key == ord('1'):
        current_view_mode = 1
        print("뷰 모드: Minimal Debug Visual")
    elif key == ord('2'):
        current_view_mode = 2
        print("뷰 모드: Binary Mask")
    elif key == ord('h'):
        show_info_text = not show_info_text
    elif key == ord('b'):
        white_flash_active = True
        flash_start_time = time.time()
    elif key == ord('n'):
        current_time = time.time()
        for i in range(NUM_CUBES):
            cube_states[i]['active'] = True
            cube_states[i]['start_time'] = current_time + i * CUBE_DELAY_PER_CUBE
            cube_states[i]['alpha'] = 0.0
            cube_states[i]['phase'] = 'fade_in'
    elif key == ord('m'):
        echo_active = not echo_active
        if echo_active:
            echo_frame_buffer.clear()
            print("에코 효과 활성화됨.")
        else:
            print("에코 효과 비활성화됨.")
    elif key == ord('v'):
        glitch_active = not glitch_active
        if glitch_active:
            print("글리치 효과 활성화됨.")
        else:
            print("글리치 효과 비활성화됨.")
    elif key == ord('r'):
        sound_engine.reset_timer()
        print("사운드 퍼포먼스 타이머 리셋.")
    elif key == ord('f'):
        # Toggle Fullscreen
        prop = cv2.getWindowProperty('Main View', cv2.WND_PROP_FULLSCREEN)
        if prop == cv2.WINDOW_FULLSCREEN:
            cv2.setWindowProperty('Main View', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        else:
            cv2.setWindowProperty('Main View', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            cv2.moveWindow('Main View', 0, 0) # 상단 여백 제거를 위해 위치 강제 조정
    elif key == ord('a'):
        auto_pilot_active = not auto_pilot_active
        print(f"오토 파일럿 {'활성화' if auto_pilot_active else '비활성화'}")
        
    return False

def process_auto_pilot(sound_engine, current_time):
    """사운드 엔진의 상태에 따라 시각 효과를 자동으로 트리거합니다."""
    global white_flash_active, flash_start_time, echo_active, glitch_active
    global cube_states, current_view_mode, last_beat_time, beat_count, auto_pilot_active

    if not auto_pilot_active:
        return

    # BPM Sync
    bpm = sound_engine.current_bpm
    beat_interval = 60.0 / bpm
    
    # 비트 감지 (시간 기반 근사치)
    if current_time - last_beat_time >= beat_interval:
        last_beat_time = current_time
        beat_count += 1
        is_strong_beat = (beat_count % 4 == 0)
        
        # Phase 0: Spectra (0-33%) - 정적, 큐브 효과
        if sound_engine.phase == 0:
            if beat_count % 16 == 0: # 16비트마다 큐브
                for i in range(NUM_CUBES):
                    cube_states[i]['active'] = True
                    cube_states[i]['start_time'] = current_time + i * CUBE_DELAY_PER_CUBE
                    cube_states[i]['alpha'] = 0.0
                    cube_states[i]['phase'] = 'fade_in'
            
            # 초기화
            if glitch_active: glitch_active = False
            if echo_active: echo_active = False
            if current_view_mode != 1: current_view_mode = 1

        # Phase 1: Pulse (33-66%) - 리듬, 플래시, 간헐적 글리치
        elif sound_engine.phase == 1:
            if is_strong_beat: # 4비트마다 플래시
                white_flash_active = True
                flash_start_time = current_time
            
            if beat_count % 8 == 0: # 8비트마다 글리치 토글
                glitch_active = not glitch_active
            
            if current_view_mode != 1: current_view_mode = 1
            if echo_active: echo_active = False

        # Phase 2: Matrix (66-100%) - 카오스, 에코, 잦은 글리치, 뷰 전환
        elif sound_engine.phase == 2:
            if beat_count % 2 == 0: # 2비트마다 플래시 (빠름)
                white_flash_active = True
                flash_start_time = current_time
            
            # 항상 글리치/에코 활성화
            if not glitch_active: glitch_active = True
            if not echo_active: echo_active = True
            
            # 4비트마다 뷰 모드 랜덤 전환
            if beat_count % 4 == 0:
                current_view_mode = 2 if random.random() > 0.6 else 1

        # Phase 3: Terminal (85-100%) - Climax
        elif sound_engine.phase == 3:
            # Extreme Flash (Every beat)
            if beat_count % 1 == 0:
                white_flash_active = True
                flash_start_time = current_time
            
            # Constant Glitch & Echo
            glitch_active = True
            echo_active = True
            
            # Rapid View Switching (Chaos)
            if beat_count % 2 == 0:
                 current_view_mode = 2 if random.random() > 0.5 else 1
            
            # Cubes go crazy
            if beat_count % 4 == 0:
                for i in range(NUM_CUBES):
                    if random.random() > 0.5:
                        cube_states[i]['active'] = True
                        cube_states[i]['start_time'] = current_time
                        cube_states[i]['alpha'] = 1.0
                        cube_states[i]['phase'] = 'fade_out'

# --- 6. 메인 함수 ---

def main():
    """프로그램의 메인 실행 루프입니다."""
    print("\n=== Shadow Art Controller ===")
    print("View Controls:")
    print("  1 - Minimal Debug Visual")
    print("  2 - Binary Mask")
    print("\nEffect Controls:")
    print("  B - Flash effect")
    print("  N - Cube animation")
    print("  M - Echo effect")
    print("  V - Glitch effect")
    print("  R - Reset Sound Timer")
    print("  H - Toggle info display")
    print("  F - Toggle Fullscreen")
    print("  A - Toggle Auto Pilot")
    print("  P - Quit")
    print("============================\n")
    
    # 6.1. 초기화
    available_indices = list_available_cameras()
    current_camera_index = CAMERA_INDEX
    if available_indices:
        current_camera_index = available_indices[0] # 첫 번째 가능한 카메라를 기본값으로
    
    try:
        user_input = input(f"사용할 카메라 인덱스를 입력하세요 (Enter for default {current_camera_index}): ")
        if user_input.strip():
            current_camera_index = int(user_input)
            print(f"카메라 인덱스 {current_camera_index}로 설정되었습니다.")
        else:
            print(f"기본 카메라 인덱스 {current_camera_index}를 사용합니다.")
    except ValueError:
        print(f"잘못된 입력입니다. 기본값 {current_camera_index}를 사용합니다.")

    try:
        cap = initialize_camera(current_camera_index, FRAME_WIDTH, FRAME_HEIGHT)
    except IOError as e:
        print(e)
        return

    # client = initialize_osc_client(OSC_IP, OSC_PORT, OSC_ADDRESS) # OSC 미사용으로 주석 처리
    setup_control_panel(FRAME_WIDTH, FRAME_HEIGHT)

    # 사운드 엔진 초기화
    try:
        sound_engine = SoundEngine()
        print("사운드 엔진 시작됨 (Ryoji Ikeda Style - 2 Min)")
    except Exception as e:
        print(f"사운드 엔진 초기화 실패: {e}")
        return

    # FPS 계산을 위한 변수
    prev_frame_time = 0

    # 6.2. 메인 루프
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("경고: 프레임을 읽을 수 없습니다. 카메라 재연결을 시도합니다...")
                time.sleep(0.1)
                cap.release()
                try:
                    cap = initialize_camera(current_camera_index, FRAME_WIDTH, FRAME_HEIGHT)
                except IOError as e:
                    print(f"카메라 재연결 실패: {e}")
                    break
                continue

            current_time = time.time()

            # 트랙바 값 읽기
            current_roi_radius, current_threshold_value, current_min_contour_area = get_trackbar_values()

            # 그림자 감지 및 데이터 계산
            shadow_data, largest_contour_found, binary_frame_masked = \
                process_frame_for_shadow(frame, FRAME_WIDTH // 2, FRAME_HEIGHT // 2, 
                                        current_roi_radius, current_threshold_value, current_min_contour_area)
            shadow_x, shadow_y, normalized_distance, angle_degrees, is_shadow_detected = shadow_data

            # Calculate Shadow Area for Sound
            shadow_area = 0.0
            if largest_contour_found is not None:
                shadow_area = cv2.contourArea(largest_contour_found)

            # OSC 메시지 전송 (주석 처리됨)
            # detection_status = int(is_shadow_detected)
            # try:
            #     if client is not None:
            #         client.send_message(OSC_ADDRESS, [shadow_x, shadow_y, normalized_distance, angle_degrees, detection_status])
            # except Exception as e:
            #     print(f"OSC 메시지 전송 실패: {e}")
            #     # OSC 전송 실패해도 계속 실행

            # 사운드 엔진 업데이트
            sound_engine.update_tracking(is_shadow_detected, shadow_x, shadow_y, normalized_distance, angle_degrees, shadow_area)

            # 오토 파일럿 처리
            process_auto_pilot(sound_engine, current_time)

            # 시각화 프레임 준비
            vis_frame = frame.copy()
            white_color = (255, 255, 255)

            # 현재 뷰 모드에 따라 표시
            if current_view_mode == 1:  # Minimal Debug Visual
                # 기본 그림자 시각화 그리기
                vis_frame = draw_base_visualization(vis_frame, FRAME_WIDTH // 2, FRAME_HEIGHT // 2, current_roi_radius, 
                                                    shadow_x, shadow_y, normalized_distance, largest_contour_found, is_shadow_detected, white_color)
                
                # 글리치 효과 적용
                global glitch_active, GLITCH_STRENGTH, GLITCH_NUM_EFFECTS
                vis_frame = apply_glitch_effect(vis_frame, glitch_active, GLITCH_STRENGTH, GLITCH_NUM_EFFECTS)

                # 에코 효과 적용
                global echo_active, ECHO_FRAMES_TO_STORE, ECHO_ALPHA_DECAY_RATE, echo_frame_buffer
                echo_frame_buffer.append(vis_frame.copy())
                vis_frame = apply_echo_effect(vis_frame, echo_active, echo_frame_buffer, ECHO_FRAMES_TO_STORE, ECHO_ALPHA_DECAY_RATE)

                # 플래시 효과 적용
                global white_flash_active, flash_start_time, white_flash_alpha
                vis_frame = apply_flash_effect(vis_frame, current_time, white_flash_active, flash_start_time, FLASH_DURATION, FADE_OUT_START_ALPHA)

                # 큐브 애니메이션 업데이트 및 그리기
                vis_frame = update_and_draw_cubes(vis_frame, current_time)

                # FPS 계산
                fps = 1 / (current_time - prev_frame_time) if (current_time - prev_frame_time) > 0 else 0
                prev_frame_time = current_time

                # 디버그 정보 오버레이 그리기
                vis_frame = draw_info_overlay(vis_frame, shadow_x, shadow_y, normalized_distance, angle_degrees, is_shadow_detected, fps, white_color, sound_engine)
                
            elif current_view_mode == 2:  # Binary Mask
                # 바이너리 마스크를 3채널로 변환하여 표시
                vis_frame = cv2.cvtColor(binary_frame_masked, cv2.COLOR_GRAY2BGR)
                
                # 바이너리 뷰에서도 ROI 원 표시
                cv2.circle(vis_frame, (FRAME_WIDTH // 2, FRAME_HEIGHT // 2), current_roi_radius, (100, 100, 100), 1)

            # 뷰 인디케이터 그리기
            draw_view_indicator(vis_frame)

            # 이미지 출력
            cv2.imshow('Main View', vis_frame)

            # 키 입력 처리
            key = cv2.waitKey(1) & 0xFF
            if handle_key_press(key, sound_engine):
                break

    except Exception as e:
        print(f"런타임 오류 발생: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 6.3. 정리 (Cleanup)
        sound_engine.close()
        cap.release()
        cv2.destroyAllWindows()
        print("카메라 및 모든 창이 해제되었습니다. 프로그램 종료.")

# 프로그램 시작점
if __name__ == "__main__":
    main()