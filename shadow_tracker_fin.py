import cv2
import numpy as np
from pythonosc import udp_client
import time
import math
import sounddevice as sd
import queue
import threading
import collections
import random

# --- 1. 설정 (Configuration) ---
CAMERA_INDEX = 0
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080

# --- OSC 설정 ---
OSC_IP = "192.168.0.2"
OSC_PORT = 8000
OSC_ADDRESS = "/shadow_data"

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

# --- 오디오 설정 ---
SAMPLERATE = 44100
BLOCKSIZE = 1024
CHANNELS = 1
AUDIO_DEVICE_INDEX = None
q = queue.Queue()

# current_fft_data는 이제 사용하지 않으므로 삭제합니다.
# current_fft_data = np.zeros(BLOCKSIZE // 2, dtype=np.float32) 
audio_data_lock = threading.Lock()

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

def initialize_osc_client(ip, port, address):
    """OSC 클라이언트를 초기화합니다."""
    try:
        client = udp_client.SimpleUDPClient(ip, port)
        print(f"OSC 클라이언트 초기화됨: {ip}:{port}, 주소: {address}")
        return client
    except Exception as e:
        print(f"OSC 클라이언트 초기화 실패: {e}")
        print("OSC 없이 계속 실행됩니다.")
        return None

def setup_control_panel(width, height):
    """디버그 및 제어판 창과 트랙바를 설정합니다."""
    def on_trackbar(val):
        pass

    cv2.namedWindow('Main View')
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

# --- 3. 오디오 처리 함수 ---

def audio_callback(indata, frames, time_info, status):
    """sounddevice로부터 오디오 데이터를 받아 큐에 넣는 콜백 함수"""
    if status:
        print(status)
    q.put(indata[::, 0])

def audio_processing_thread_func():
    """오디오 데이터를 처리 (FFT)하고 전역 변수를 업데이트하는 스레드 함수."""
    # global current_fft_data # 더 이상 사용하지 않으므로 제거합니다.
    try:
        with sd.InputStream(samplerate=SAMPLERATE, blocksize=BLOCKSIZE,
                            channels=CHANNELS, callback=audio_callback,
                            device=AUDIO_DEVICE_INDEX):
            print("\n--- 오디오 스트림 시작 ---")
            print(f"오디오 장치: {sd.query_devices(AUDIO_DEVICE_INDEX, 'input')['name'] if AUDIO_DEVICE_INDEX is not None else '기본 입력 장치'}")
            print(f"샘플링 레이트: {SAMPLERATE} Hz")
            print(f"블록 크기 (FFT): {BLOCKSIZE} 샘플")
            print("------------------------\n")
            
            while True:
                try:
                    audio_block = q.get(timeout=1.0)
                    
                    # FFT 계산은 더 이상 시각화에 필요 없으므로 제거합니다.
                    # window = np.hanning(len(audio_block))
                    # windowed_block = audio_block * window
                    # fft_result = np.fft.rfft(windowed_block)
                    # amplitude_spectrum = np.abs(fft_result) / BLOCKSIZE
                    # min_db = -60
                    # max_db = 0
                    # amplitude_spectrum_log = 20 * np.log10(amplitude_spectrum + 1e-10)
                    # normalized_spectrum = (amplitude_spectrum_log - min_db) / (max_db - min_db)
                    # normalized_spectrum = np.clip(normalized_spectrum, 0, 1)
                    
                    with audio_data_lock:
                        # current_fft_data = normalized_spectrum # 이 줄은 더 이상 필요 없으므로 제거합니다.
                        pass # FFT 데이터 업데이트 대신, 이제는 아무것도 하지 않습니다.
                        
                except queue.Empty:
                    pass
                except Exception as e:
                    print(f"오디오 처리 스레드 내부 오류: {e}")
                    break
    except Exception as e:
        print(f"오디오 스트림 초기화 오류: {e}")

# --- 4. 핵심 이미지 처리 함수 ---

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

# --- 5. 시각화 및 효과 함수 ---

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

def draw_info_overlay(vis_frame, shadow_x, shadow_y, normalized_distance, angle_degrees, is_shadow_detected, fps, white_color):
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
        
        fps_text = f"FPS: {int(fps)}"
        cv2.putText(vis_frame, fps_text, (FRAME_WIDTH - 150, 30), font, font_scale, white_color, font_thickness)

        cv2.putText(vis_frame, f'Info text toggle: Press H', (10, FRAME_HEIGHT - 10), cv2.FONT_HERSHEY_PLAIN, 1, white_color, 1)
    return vis_frame

def draw_view_indicator(frame):
    """현재 뷰 모드를 표시합니다."""
    global current_view_mode
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    view_text = f"View: {'[1] Visual' if current_view_mode == 1 else '[2] Binary'}"
    cv2.putText(frame, view_text, (FRAME_WIDTH - 200, FRAME_HEIGHT - 20), 
                font, 0.6, (255, 255, 255), 1)

# --- 6. 키 입력 처리 함수 ---

def handle_key_press(key):
    """키 입력 이벤트를 처리하고 관련 전역 상태를 업데이트합니다."""
    global show_info_text, white_flash_active, flash_start_time, echo_active, glitch_active
    global cube_states, current_view_mode

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
    return False

# --- 7. 메인 함수 ---

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
    print("  H - Toggle info display")
    print("  P - Quit")
    print("============================\n")
    
    # 7.1. 초기화
    try:
        cap = initialize_camera(CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT)
    except IOError as e:
        print(e)
        return

    client = initialize_osc_client(OSC_IP, OSC_PORT, OSC_ADDRESS)
    setup_control_panel(FRAME_WIDTH, FRAME_HEIGHT)

    audio_thread = threading.Thread(target=audio_processing_thread_func, daemon=True)
    audio_thread.start()

    # FPS 계산을 위한 변수
    prev_frame_time = 0

    # 7.2. 메인 루프
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("경고: 프레임을 읽을 수 없습니다. 카메라 재연결을 시도합니다...")
                try:
                    if client is not None:
                        client.send_message(OSC_ADDRESS, [-1, -1, -1.0, -1.0, 0])
                except Exception as e:
                    print(f"OSC 오류 메시지 전송 실패: {e}")
                time.sleep(0.1)
                cap.release()
                try:
                    cap = initialize_camera(CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT)
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

            # OSC 메시지 전송
            detection_status = int(is_shadow_detected)
            try:
                if client is not None:
                    client.send_message(OSC_ADDRESS, [shadow_x, shadow_y, normalized_distance, angle_degrees, detection_status])
            except Exception as e:
                print(f"OSC 메시지 전송 실패: {e}")
                # OSC 전송 실패해도 계속 실행

            # 시각화 프레임 준비
            vis_frame = frame.copy()
            white_color = (255, 255, 255)

            # 현재 뷰 모드에 따라 표시
            if current_view_mode == 1:  # Minimal Debug Visual
                # 기본 그림자 시각화 그리기
                vis_frame = draw_base_visualization(vis_frame, FRAME_WIDTH // 2, FRAME_HEIGHT // 2, current_roi_radius, 
                                                    shadow_x, shadow_y, normalized_distance, largest_contour_found, is_shadow_detected, white_color)
                
                # --- 오른쪽 아래 오디오 스펙트럼 바 삭제됨 ---
                # draw_audio_visualizer(vis_frame, white_color) 호출이 삭제되었습니다.

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
                vis_frame = draw_info_overlay(vis_frame, shadow_x, shadow_y, normalized_distance, angle_degrees, is_shadow_detected, fps, white_color)
                
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
            if handle_key_press(key):
                break

    except Exception as e:
        print(f"런타임 오류 발생: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 7.3. 정리 (Cleanup)
        cap.release()
        cv2.destroyAllWindows()
        print("카메라 및 모든 창이 해제되었습니다. 프로그램 종료.")

# 프로그램 시작점
if __name__ == "__main__":
    main()