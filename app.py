import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import time
import traceback

# ==========================================
# 0. 로그 및 초기화
# ==========================================
def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

if 'system_logs' not in st.session_state:
    st.session_state['system_logs'] = []

def add_log(msg, level="INFO"):
    timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    icon = "✅" if level == "INFO" else "🚨"
    st.session_state['system_logs'].insert(0, f"[{timestamp}] {icon} {msg}")

# ==========================================
# 1. DB 연결 (영구 캐싱)
# ==========================================
@st.cache_resource
def get_cached_sheet_object():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_json" in st.secrets:
            creds_dict = json.loads(st.secrets["gcp_json"])
        else:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sh = client.open("bus_schedule_db")
        return sh
    except Exception as e:
        st.error(f"❌ 구글 연결 실패: {e}")
        return None

def get_db_connection():
    sh = get_cached_sheet_object()
    if sh: return sh
    st.stop()

@st.cache_data(ttl=600)
def load_data(sheet_name):
    sh = get_db_connection()
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_values()
        if not data: return pd.DataFrame()
        headers = data.pop(0)
        return pd.DataFrame(data, columns=headers)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

def clear_cache_after_save():
    st.cache_data.clear()

# ==========================================
# 2. 인증 및 계정
# ==========================================
def make_hash(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def login_user(username, password):
    df = load_data("users")
    if df.empty: return None
    pw_hash = make_hash(password)
    df['username'] = df['username'].astype(str)
    user = df[(df['username'] == username) & (df['password'] == pw_hash)]
    if not user.empty:
        return user.iloc[0]['role'], user.iloc[0]['name']
    return None

def add_user_account(username, password, role, name):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    k_date = get_kst_now().strftime("%Y-%m-%d")
    new_row = [username, make_hash(password), role, name, k_date]
    ws.append_row(new_row)
    clear_cache_after_save()
    return True

def delete_user_account(username):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        cell = ws.find(username)
        if cell:
            ws.delete_rows(cell.row)
            clear_cache_after_save()
    except: pass

def update_user_password(username, new_password):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        cell = ws.find(username)
        if cell:
            ws.update_cell(cell.row, 2, make_hash(new_password))
            clear_cache_after_save()
            return True
    except: pass
    return False

# ==========================================
# 3. 데이터 저장 (가장 빠른 버전)
# ==========================================
def add_driver_with_group(name, group_name, start_date="2020-01-01"):
    sh = get_db_connection()
    ws_drivers = sh.worksheet("drivers")
    created_at = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        existing = ws_drivers.find(name)
        if not existing:
            ws_drivers.append_row(["", name, group_name, created_at, ""])
    except: pass
    ws_history = sh.worksheet("group_history")
    ws_history.append_row(["", name, group_name, start_date, created_at])
    clear_cache_after_save()
    return True

def set_driver_resignation(name, r_date):
    sh = get_db_connection()
    ws = sh.worksheet("drivers")
    try:
        cell = ws.find(name)
        if cell:
            ws.update_cell(cell.row, 5, r_date)
            clear_cache_after_save()
    except: pass

def delete_driver(driver_name):
    sh = get_db_connection()
    ws_d = sh.worksheet("drivers")
    try:
        cell = ws_d.find(driver_name)
        if cell: ws_d.delete_rows(cell.row)
    except: pass
    ws_h = sh.worksheet("group_history")
    try:
        cells = ws_h.findall(driver_name)
        for cell in reversed(cells): ws_h.delete_rows(cell.row)
    except: pass
    ws_s = sh.worksheet("schedules")
    try:
        cells = ws_s.findall(driver_name)
        for cell in reversed(cells): ws_s.delete_rows(cell.row)
    except: pass
    clear_cache_after_save()

# [저장] 쓰기 전용 함수 (1개 값 반환)
def save_range_batch(name_list, start, end, type, shift, note):
    dates = pd.date_range(start, end)
    now_kst = get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    base_id = now_kst.strftime("%y%m%d%H%M") 
    
    rows_to_add = []
    count = 0
    for name in name_list:
        for d in dates:
            d_str = d.strftime("%Y-%m-%d")
            row_id = f"{base_id}{count:02d}"
            rows_to_add.append([row_id, name, d_str, type, note, created_at, shift])
            count += 1
            
    if rows_to_add:
        sh = get_db_connection()
        ws = sh.worksheet("schedules")
        ws.append_rows(rows_to_add)
        clear_cache_after_save()
        
    return len(rows_to_add)

def add_company_event(date, title):
    sh = get_db_connection()
    ws = sh.worksheet("company_events")
    now_kst = get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d")
    row_id = now_kst.strftime("%y%m%d%H%M%S")
    ws.append_row([row_id, date, title, created_at])
    clear_cache_after_save()

# ==========================================
# 4. 로직 및 계산
# ==========================================
WEEKDAY_KOREAN = ["월", "화", "수", "목", "금", "토", "일"]
SORT_ORDER = {"휴무": 1, "교육": 2, "경조사": 3, "징계": 4, "당일 해지": 5, "기타": 6, "휴직": 7, "병가": 8}

def calculate_auto_shift(group_name, target_date_str):
    if not group_name or "조" not in group_name: return None
    try:
        ref = datetime(2025, 12, 1)
        tgt = datetime.strptime(target_date_str, "%Y-%m-%d")
        pat = ["오전", "오전", "오전", "오전", "휴무", "오후", "오후", "오후", "오후", "휴무"]
        offs = {"10조":0, "9조":1, "8조":2, "7조":3, "6조":4, "5조":5, "4조":6, "3조":7, "2조":8, "1조":9}
        off = offs.get(group_name)
        if off is None: return None
        return pat[((tgt - ref).days + off) % 10]
    except: return None

def get_group_from_dict(history_dict, name, target_date_str):
    if name not in history_dict: return None
    records = history_dict[name]
    for start_date, group in records:
        if start_date <= target_date_str:
            return group
    return None

def get_driver_group_by_name(name):
    df = load_data("drivers")
    if df.empty or 'name' not in df.columns: return None
    df['name'] = df['name'].astype(str)
    row = df[df['name'] == name]
    if not row.empty:
        return row.iloc[0]['group_name']
    return None

def get_type_color(type_name):
    colors = { 
        "휴무": "#2b8a3e", "육아휴직": "#f59f00", "휴직": "#f59f00", "경조사": "#6741d9", 
        "병가": "#c92a2a", "교육": "#d97706", "징계": "#000000", "당일 해지": "#e03131", "기타": "#343a40" 
    }
    return colors.get(type_name, "#1c7ed6")

def get_off_groups(date_str):
    ref = datetime(2025, 12, 1)
    target = datetime.strptime(date_str, "%Y-%m-%d")
    cycle = (target - ref).days % 5
    return [("1,6조", ["1조", "6조"]), ("2,7조", ["2조", "7조"]), ("3,8조", ["3조", "8조"]), ("4,9조", ["4조", "9조"]), ("5,10조", ["5조", "10조"])][cycle]

def is_holiday(date_obj):
    holidays = [
        "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
        "2024-03-01", "2024-04-10", "2024-05-05", "2024-05-06", "2024-05-15",
        "2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18",
        "2024-10-03", "2024-10-09", "2024-12-25",
        "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-01",
        "2025-05-05", "2025-05-06", "2025-06-06", "2025-08-15", "2025-10-03",
        "2025-10-06", "2025-10-09", "2025-12-25"
    ]
    return date_obj.strftime("%Y-%m-%d") in holidays

def get_daily_shift_summary(date_str):
    am, pm, off = [], [], []
    for i in range(1, 11):
        s = calculate_auto_shift(f"{i}조", date_str)
        if s == "오전": am.append(str(i))
        elif s == "오후": pm.append(str(i))
        else: off.append(str(i))
    am_str = f"<span style='color:#1c7ed6; font-weight:bold;'>오전: {','.join(am)}</span>" if am else ""
    pm_str = f"<span style='color:#d9480f; font-weight:bold;'>오후: {','.join(pm)}</span>" if pm else ""
    return f"{am_str}<br>{pm_str}"

@st.cache_data(ttl=600)
def calculate_layout_rows(df_month):
    if df_month.empty: return {}, 0
    df_sorted = df_month.sort_values(by=['name', 'date'])
    segments = []
    if not df_sorted.empty:
        curr = df_sorted.iloc[0]
        c_name, c_type, c_start, c_end = curr['name'], curr['type'], curr['date'], curr['date']
        c_recs = [curr]
        for i in range(1, len(df_sorted)):
            row = df_sorted.iloc[i]
            pd_date = datetime.strptime(c_end, "%Y-%m-%d")
            cd = datetime.strptime(row['date'], "%Y-%m-%d")
            if row['name'] == c_name and row['type'] == c_type and (cd - pd_date).days == 1:
                c_end = row['date']
                c_recs.append(row)
            else:
                segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
                c_name, c_type, c_start, c_end = row['name'], row['type'], row['date'], row['date']
                c_recs = [row]
        segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
    
    segments.sort(key=lambda x: (SORT_ORDER.get(x['type'], 99), x['start'], (datetime.strptime(x['end'], "%Y-%m-%d") - datetime.strptime(x['start'], "%Y-%m-%d")).days * -1))
    lanes = {} 
    layout_map = {} 
    for seg in segments:
        seg_dates = [rec['date'] for rec in seg['records']]
        assigned_row = 0
        while True:
            is_occupied = False
            if assigned_row in lanes:
                for d in seg_dates:
                    if d in lanes[assigned_row]:
                        is_occupied = True
                        break
            if not is_occupied: break
            assigned_row += 1
        if assigned_row not in lanes: lanes[assigned_row] = set()
        lanes[assigned_row].update(seg_dates)
        recs = seg['records']
        total_len = len(recs)
        for idx, rec in enumerate(recs):
            is_start = (idx == 0)
            is_end = (idx == total_len - 1)
            layout_map[(rec['date'], assigned_row)] = { 'rec': rec, 'is_start': is_start, 'is_end': is_end, 'duration': total_len }
    max_row = max(lanes.keys()) + 1 if lanes else 0
    return layout_map, max_row

def get_stats_optimized(date_str, all_drivers_df, today_schedules_df, history_dict):
    total = len(all_drivers_df)
    am_cnt, pm_cnt, off_cnt = 0, 0, 0
    
    if not today_schedules_df.empty and 'shift' not in today_schedules_df.columns:
        today_schedules_df['shift'] = '자동'

    manual_map = {}
    if not today_schedules_df.empty:
        for _, row in today_schedules_df.iterrows():
            manual_map[row['name']] = (row['type'], row.get('shift', '자동'))
    
    drivers_list = all_drivers_df['name'].tolist() if not all_drivers_df.empty else []
    
    for name in drivers_list:
        final_shift = None
        if name in manual_map:
            typ, sft = manual_map[name]
            if typ == '휴무': final_shift = '휴무'
            elif sft and sft != '자동': final_shift = sft
        
        if not final_shift:
            grp = get_group_from_dict(history_dict, name, date_str)
            if grp:
                final_shift = calculate_auto_shift(grp, date_str)
        
        if final_shift == '오전': am_cnt += 1
        elif final_shift == '오후': pm_cnt += 1
        elif final_shift == '휴무': off_cnt += 1
            
    full_text = f"총 {total}명 (오전:{am_cnt}, 오후:{pm_cnt}, 휴무:{off_cnt})"
    short_text = f"총 {total} / 전 {am_cnt} / 후 {pm_cnt}"
    return full_text, short_text

def get_streak_info(full_schedule_map, p_name, p_date_str, p_type):
    if (p_name, p_date_str) not in full_schedule_map: return "", "", ""
    curr = datetime.strptime(p_date_str, "%Y-%m-%d")
    start_date, end_date = curr, curr
    
    while True:
        prev_d = (start_date - timedelta(days=1)).strftime("%Y-%m-%d")
        if (p_name, prev_d) in full_schedule_map and full_schedule_map[(p_name, prev_d)] == p_type: 
            start_date -= timedelta(days=1)
        else: break
    
    while True:
        next_d = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
        if (p_name, next_d) in full_schedule_map and full_schedule_map[(p_name, next_d)] == p_type: 
            end_date += timedelta(days=1)
        else: break
        
    duration = (end_date - start_date).days + 1
    prefix, suffix = "", ""
    period_text = f"(~{end_date.month}/{end_date.day})"
    if duration >= 2:
        is_start = (p_date_str == start_date.strftime("%Y-%m-%d"))
        is_end = (p_date_str == end_date.strftime("%Y-%m-%d"))
        if is_start: prefix = "➡️"; 
        if is_end: suffix = "🛑"
    return prefix, suffix, period_text

# ==========================================
# 5. 화면 렌더링 (팝업 고정 및 에러 유지)
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
        .red-button > button { background-color: #FF4B4B !important; color: white !important; font-weight: bold !important; }
        .red-button > button:hover { background-color: #D93A3A !important; }
        div[data-testid="column"] { padding: 0px !important; gap: 0px !important; }
        .horizontal-scroll-container { display: flex; overflow-x: auto; gap: 0px; padding-bottom: 15px; width: 100%; }
        .calendar-day-box { border-right: 1px solid #e9ecef; border-top: 1px solid #e9ecef; border-bottom: 1px solid #e9ecef; border-left: 0; min-height: 200px; padding: 0; background-color: white; display: flex; flex-direction: column; height: auto !important; }
        .calendar-day-box:first-child { border-left: 1px solid #e9ecef; }
        .calendar-day-box-horiz { flex: 0 0 90px; } 
        .calendar-day-box-grid { width: 100%; border: 1px solid #e9ecef; margin: 2px; }
        .horizontal-scroll-container::-webkit-scrollbar { height: 8px; }
        .horizontal-scroll-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        .horizontal-scroll-container::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
        .horizontal-scroll-container::-webkit-scrollbar-thumb:hover { background: #aaa; }
        .daily-stats-box { background-color: #f1f3f5; border-bottom: 1px solid #e9ecef; font-size: 11px; text-align: center; padding: 3px 0; color: #495057; font-weight: bold; white-space: nowrap; }
        .group-info-box { font-size: 10px; padding: 2px 4px; background-color: #fff; border-bottom: 1px solid #f1f3f5; line-height: 1.2; font-weight: bold; }
        .event-container { height: 46px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; border-bottom: 1px solid #f1f3f5; padding: 2px 1px; background-color: #fff; }
        .event-container::-webkit-scrollbar { display: none; }
        .day-header { display: flex; flex-direction: column; padding-top: 4px; padding-bottom: 4px; gap: 1px; justify-content: center; background-color: #fff; border-bottom: 1px solid #eee; }
        .schedule-bar { color: white; padding: 0 2px; margin-bottom: 1px; line-height: 1.1; text-align: center; cursor: help; font-size: 11px; height: 34px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; border-top: 1px solid rgba(0,0,0,0.1); border-bottom: 1px solid rgba(0,0,0,0.1); }
        .bar-start { border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0; border-bottom-right-radius: 0; margin-right: -10px !important; margin-left: 2px; position: relative; z-index: 2; }
        .bar-mid { border-radius: 0; border-left: none; border-right: none; margin-left: -10px !important; margin-right: -10px !important; position: relative; z-index: 1; }
        .bar-end { border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-top-left-radius: 0; border-bottom-left-radius: 0; margin-left: -10px !important; margin-right: 2px; position: relative; z-index: 2; }
        .bar-single { border-radius: 4px; margin: 0 2px 1px 2px; z-index: 3; }
        .schedule-spacer { height: 34px; margin-bottom: 1px; background-color: transparent; }
        .login-btn > button { background-color: #FF4B4B !important; color: white !important; width: 100%; font-weight: bold; border-radius: 5px; padding: 10px; }
        .login-btn > button:hover { background-color: #D93A3A !important; }
        @media (max-width: 640px) { h1 { font-size: 1.6rem !important; } .mobile-font { font-size: 10px !important; } .mobile-header { font-size: 11px !important; } }
    </style>
    """, unsafe_allow_html=True)

@st.dialog("➕ 빠른 등록")
def show_input_dialog():
    tab1, tab2 = st.tabs(["👤 승무원 일정", "🏢 회사 행사"])
    with tab1:
        st.write("달력을 보면서 바로 입력하세요.")
        names_str = st.text_area("이름 (엔터 구분)", height=100, key="quick_names")
        rng = st.date_input("기간", [], help="시작/종료일 선택", key="quick_range")
        if names_str and len(rng) > 0:
            st.caption(f"{len(names_str.split())}명 선택됨")
        c1, c2 = st.columns(2)
        with c1: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="quick_type")
        with c2: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="quick_shift")
        nte = st.text_input("비고", key="quick_note")
        
        # [수정] 성공 시 토스트 띄우고 즉시 새로고침, 실패 시 정지
        if st.button("승무원 일정 저장", type="primary", use_container_width=True):
            if names_str and len(rng) > 0:
                lst = [n.strip() for n in names_str.replace(',', '\n').split('\n') if n.strip()]
                try:
                    with st.spinner('저장 중입니다...'):
                        # save_range_batch 함수가 1개의 값(count)만 반환하도록 맞춰져 있음
                        count = save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
                    
                    # 성공 시 Toast 메시지 (Rerun 되어도 사라지지 않음)
                    st.toast("✅ 저장 완료! 잠시 후 갱신됩니다.", icon="🔄")
                    add_log(f"입력 성공: {len(lst)}명, {rng[0]}~{rng[-1]}, {typ}")
                    
                    # 0.5초만 짧게 대기 후 즉시 리로딩 (자동 새로고침)
                    time.sleep(0.5)
                    st.rerun()
                    
                except Exception as e:
                    error_msg = f"{str(e)}\n{traceback.format_exc()}"
                    add_log(error_msg, "ERROR")
                    st.error("🚨 저장 중 오류 발생!")
                    st.text_area("에러 상세 (복사 가능)", error_msg, height=200)
                    st.stop() # 에러 발생 시 여기서 멈춰서 팝업 유지
            else:
                st.warning("이름과 기간을 입력해주세요.")

    with tab2:
        st.write("회사 주요 행사를 달력 상단에 표시합니다.")
        ed_list = st.date_input("행사 기간", [], help="시작/종료일", key="quick_event_range")
        et = st.text_input("행사 내용", key="quick_event_title")
        if st.button("회사 행사 저장", type="primary", use_container_width=True, key="quick_event_save"):
            if et and len(ed_list) > 0:
                try:
                    with st.spinner('저장 중입니다...'):
                        s_d, e_d = ed_list[0], ed_list[1] if len(ed_list)>1 else ed_list[0]
                        for d in pd.date_range(s_d, e_d): add_company_event(d.strftime("%Y-%m-%d"), et)
                        st.cache_data.clear()
                    
                    st.toast("✅ 행사 저장 완료!", icon="🔄")
                    time.sleep(0.5)
                    st.rerun()
                    
                except Exception as e:
                    error_msg = f"{str(e)}\n{traceback.format_exc()}"
                    add_log(f"행사 저장 실패: {str(e)}", "ERROR")
                    st.error("오류 발생")
                    st.text_area("에러 상세", error_msg, height=200)
                    st.stop()
            else: st.warning("기간과 내용을 모두 입력해주세요.")

def render_log_tab():
    st.subheader("🔧 시스템 로그 (관리자 전용)")
    if st.button("🗑️ 로그 비우기"):
        st.session_state['system_logs'] = []
        st.rerun()
    if st.session_state['system_logs']:
        log_text = "\n".join(st.session_state['system_logs'])
        st.text_area("로그 내역", log_text, height=400)
    else:
        st.info("기록된 로그가 없습니다.")

# [중요] 렌더링 에러 방지용 Wrapper 함수
def render_calendar_tab():
    try:
        _render_calendar_tab_unsafe()
    except Exception:
        st.error("🚨 캘린더를 그리는 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())

def _render_calendar_tab_unsafe():
    st.subheader("📅 전체 월간 휴무 현황")
    inject_custom_css()
    now = get_kst_now()
    if 'view_year' not in st.session_state: st.session_state.view_year = now.year
    if 'view_month' not in st.session_state: st.session_state.view_month = now.month
    c_prev, c_ym, c_next, c_view, c_btn = st.columns([0.5, 1.5, 0.5, 1.5, 1])
    with c_prev:
        if st.button("◀", use_container_width=True):
            if st.session_state.view_month == 1:
                st.session_state.view_year -= 1; st.session_state.view_month = 12
            else: st.session_state.view_month -= 1
            st.rerun()
    with c_ym: st.markdown(f"<h3 style='text-align:center; margin:0; padding-top:5px;'>{st.session_state.view_year}년 {st.session_state.view_month}월</h3>", unsafe_allow_html=True)
    with c_next:
        if st.button("▶", use_container_width=True):
            if st.session_state.view_month == 12:
                st.session_state.view_year += 1; st.session_state.view_month = 1
            else: st.session_state.view_month += 1
            st.rerun()
    with c_view: view_mode = st.radio("보기 방식", ["가로 스크롤 (타임라인)", "기본 달력 (그리드)"], horizontal=True, label_visibility="collapsed")
    with c_btn:
        if st.session_state.get('auth_status') == 'admin':
            if st.button("➕ 빠른 입력", type="primary", use_container_width=True): show_input_dialog()
    st.divider()
    
    selected_year = st.session_state.view_year
    selected_month = st.session_state.view_month
    
    df = load_data("schedules")
    
    # [수정] 렌더링은 해당 월만 필터링 (화면 그리기 용)
    if not df.empty:
        filter_keyword = f"{selected_year}-{selected_month:02d}"
        df_month = df[df['date'].astype(str).str.startswith(filter_keyword)]
    else:
        df_month = pd.DataFrame(columns=['id', 'name', 'date', 'type', 'shift', 'note', 'created_at'])

    # [수정] 휴무 연속성 계산은 전체 데이터(df)로 맵핑 (월 넘어가도 계산되게)
    full_schedule_map = {}
    if not df.empty:
        for _, row in df.iterrows(): full_schedule_map[(row['name'], str(row['date']))] = row['type']

    df_events = load_data("company_events")
    if not df_events.empty:
        df_events_month = df_events[df_events['date'].astype(str).str.startswith(f"{selected_year}-{selected_month:02d}")]
    else:
        df_events_month = pd.DataFrame(columns=['id', 'date', 'title', 'created_at'])

    all_drivers = load_data("drivers")
    group_history_df = load_data("group_history")
    
    history_dict = {}
    if not group_history_df.empty and 'driver_name' in group_history_df.columns:
        for idx, row in group_history_df.iterrows():
            d_name = row['driver_name']
            if d_name not in history_dict: history_dict[d_name] = []
            history_dict[d_name].append((row['start_date'], row['group_name']))
        for d_name in history_dict:
            history_dict[d_name].sort(key=lambda x: x[0], reverse=True)
    
    _, last_day = calendar.monthrange(selected_year, selected_month)

    def get_day_html(day, is_horiz=True):
        cur_date = datetime(selected_year, selected_month, day)
        date_str = cur_date.strftime("%Y-%m-%d")
        off_group_str, _ = get_off_groups(date_str)
        wd_idx = cur_date.weekday()
        wd_str = WEEKDAY_KOREAN[wd_idx]
        
        group_shift_html = get_daily_shift_summary(date_str)
        today_schedules = pd.DataFrame()
        if not df_month.empty:
            today_schedules = df_month[df_month['date'] == date_str].copy()
            
        full_stat, short_stat = get_stats_optimized(date_str, all_drivers, today_schedules, history_dict)
        
        today_events = pd.DataFrame()
        if not df_events_month.empty:
            today_events = df_events_month[df_events_month['date'] == date_str]
            
        count = len(today_schedules)
        is_today = date_str == now.strftime("%Y-%m-%d")
        tomorrow = now + timedelta(days=1)
        is_tomorrow = date_str == tomorrow.strftime("%Y-%m-%d")
        
        if is_today:
            bg_color = "#fff9c4"
            border_style = "1px solid #fbc02d; box-shadow: inset 0 0 5px rgba(251, 192, 45, 0.5);"
        elif is_tomorrow: 
            bg_color = "#ffe3e3" 
            border_style = "1px solid #e03131; box-shadow: inset 0 0 5px rgba(224, 49, 49, 0.5);"
        else:
            bg_color = "white"
            border_style = "1px solid #e9ecef"
            
        day_color = "#333"
        if wd_idx == 6 or is_holiday(cur_date): day_color = "#d32f2f"
        elif wd_idx == 5: day_color = "#1976D2"
        
        box_class = "calendar-day-box calendar-day-box-horiz" if is_horiz else "calendar-day-box calendar-day-box-grid"
        html = f'<div class="{box_class}" style="background-color:{bg_color}; border:{border_style};">'
        html += f'<div class="day-header"><div style="width:100%; display:flex; justify-content:space-between; align-items:center; padding:0 3px;"><span style="font-size:14px; font-weight:bold; color:{day_color};">{day}일({wd_str})</span>'
        if count > 0: html += f'<span style="font-size:11px; font-weight:bold; color:#333;">{count}명</span>'
        html += f'</div><div class="group-info-box">{group_shift_html}</div></div>'
        
        if is_horiz: html += f'<div class="daily-stats-box" title="{full_stat}">{short_stat}</div>'
        
        html += '<div class="event-container">'
        if not today_events.empty:
            for _, evt in today_events.iterrows():
                html += f"<div style='background-color:#E3F2FD; color:#1565C0; padding:1px; border-radius:3px; font-size:10px; font-weight:bold; text-align:center; border:1px solid #BBDEFB; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>{evt['title']}</div>"
        html += '</div>'
        
        if not is_horiz and not today_schedules.empty:
            today_schedules['sort_rank'] = today_schedules['type'].map(lambda x: SORT_ORDER.get(x, 99))
            today_schedules = today_schedules.sort_values(by=['sort_rank', 'name'])
            for _, row in today_schedules.iterrows():
                color = get_type_color(row['type'])
                prefix, suffix, period_text = get_streak_info(full_schedule_map, row['name'], date_str, row['type'])
                eff_grp = get_group_from_dict(history_dict, row['name'], date_str)
                orig_shift = calculate_auto_shift(eff_grp, date_str)
                p_tip = f"원래 근무: {orig_shift if orig_shift else '없음'} ({eff_grp})"
                s_info = ""
                hide_st = ["병가", "육아휴직", "휴직", "당일 해지"]
                if st.session_state.get('auth_status') == 'admin' and row['shift'] and row['shift'] not in ['휴무', '기타', '자동'] and row['type'] not in hide_st:
                    s_info = f"[{row['shift']}] "
                name_line = f"""<div style="display:flex; align-items:center; justify-content:center;"><div style="width:12px; text-align:left;">{prefix}</div><div style="flex:1; text-align:center;">{s_info}{row['name']}</div><div style="width:12px; text-align:right;">{suffix}</div></div>"""
                if row['type'] == '휴무':
                    i_html = f"<div style='font-size:12px; font-weight:bold;'>{name_line}</div>"
                    if period_text: i_html += f"<div style='font-size:9px; opacity:0.9;'>{period_text}</div>"
                else:
                    n_txt = row['note'] if row['note'] else row['type']
                    if period_text: n_txt += f" {period_text}"
                    i_html = f"<div style='font-size:12px; font-weight:bold;'>{name_line}</div><div style='font-size:9px; opacity:0.9;'>{n_txt}</div>"
                html += f"<div class='schedule-bar bar-single' style='background-color:{color};' title='{p_tip}'>{i_html}</div>"
        html += '</div>'
        return html

    if "가로" in view_mode:
        layout_map, max_rows = calculate_layout_rows(df_month)
        html_content = '<div class="horizontal-scroll-container">'
        for day in range(1, last_day + 1):
            cur_date = datetime(selected_year, selected_month, day)
            date_str = cur_date.strftime("%Y-%m-%d")
            prev_date_str = (cur_date - timedelta(days=1)).strftime("%Y-%m-%d")
            day_html = get_day_html(day, is_horiz=True)
            html_content += day_html[:-6] 
            for r_idx in range(max_rows):
                if (date_str, r_idx) in layout_map:
                    item = layout_map[(date_str, r_idx)]
                    row = item['rec']
                    violation_marker = ""
                    my_shift = row.get('shift', '자동')
                    if my_shift == '자동':
                        grp = get_group_from_dict(history_dict, row['name'], date_str)
                        my_shift = calculate_auto_shift(grp, date_str)
                    prev_grp = get_group_from_dict(history_dict, row['name'], prev_date_str)
                    prev_shift = calculate_auto_shift(prev_grp, prev_date_str)
                    if prev_shift == '오후' and my_shift == '오전':
                        violation_marker = "<div style='position:absolute; top:0; left:0; width:6px; height:6px; background-color:red; border-radius:50%; z-index:20;' title='⚠️ 휴식 시간 부족 (전날 오후 -> 금일 오전)'></div>"
                    duration = item['duration']
                    color = get_type_color(row['type'])
                    prefix, suffix, period_text = get_streak_info(full_schedule_map, row['name'], date_str, row['type'])
                    eff_grp = get_group_from_dict(history_dict, row['name'], date_str)
                    orig_shift = calculate_auto_shift(eff_grp, date_str)
                    personal_tooltip = f"원래 근무: {orig_shift if orig_shift else '없음'} ({eff_grp})"
                    s_info = ""
                    hide_shift_types = ["병가", "육아휴직", "휴직", "당일 해지"]
                    if st.session_state.get('auth_status') == 'admin' and row['shift'] and row['shift'] not in ['휴무', '기타', '자동'] and row['type'] not in hide_shift_types:
                        s_info = f"[{row['shift']}] "
                    bar_class = "bar-single"
                    if duration >= 2:
                        if item['is_start']: bar_class = "bar-start"
                        elif item['is_end']: bar_class = "bar-end"
                        else: bar_class = "bar-mid"
                    border_style = ""
                    if row['type'] in ['휴무', '경조사']:
                        border_style = "border-top: 3px solid black; border-bottom: 3px solid black;"
                        if bar_class == "bar-start": border_style += "border-left: 3px solid black;"
                        elif bar_class == "bar-end": border_style += "border-right: 3px solid black;"
                        elif bar_class == "bar-single": border_style = "border: 2px solid black;"
                    else: border_style = "border: none;"
                    name_line = f"""<div style="display:flex; align-items:center; justify-content:center;"><div style="width:12px; text-align:left;">{prefix}</div><div style="flex:1; text-align:center;">{s_info}{row['name']}</div><div style="width:12px; text-align:right;">{suffix}</div></div>"""
                    if row['type'] == '휴무':
                        inner_html = f"<div style='font-size:12px; font-weight:bold;'>{name_line}</div>"
                        if period_text: inner_html += f"<div style='font-size:9px; opacity:0.9;'>{period_text}</div>"
                    else:
                        note_text = row['note'] if row['note'] else row['type']
                        if period_text: note_text += f" {period_text}"
                        inner_html = f"<div style='font-size:12px; font-weight:bold;'>{name_line}</div><div style='font-size:9px; opacity:0.9;'>{note_text}</div>"
                    html_content += f"<div class='schedule-bar {bar_class}' style='background-color:{color}; {border_style}; position:relative;' title='{personal_tooltip}'>{violation_marker}{inner_html}</div>"
                else: html_content += "<div class='schedule-spacer'></div>"
            html_content += '</div>'
        html_content += '</div>'
        st.markdown(html_content, unsafe_allow_html=True)
    else:
        cal = calendar.monthcalendar(selected_year, selected_month)
        cols = st.columns(7)
        for i, day_name in enumerate(WEEKDAY_KOREAN):
            color = "#d32f2f" if i==6 else "#1976D2" if i==5 else "black"
            cols[i].markdown(f"<div style='text-align: center; color: {color}; font-weight:bold; font-size:14px; border-bottom:2px solid #333; padding-bottom:5px;'>{day_name}</div>", unsafe_allow_html=True)
        for week in cal:
            cols = st.columns(7)
            for i, day in enumerate(week):
                with cols[i]:
                    if day == 0: st.markdown("<div class='calendar-day-box' style='background-color:#f8f9fa; min-height:200px;'></div>", unsafe_allow_html=True)
                    else: st.markdown(get_day_html(day, is_horiz=False), unsafe_allow_html=True)

def render_input_tab():
    st.subheader("📝 관리자 입력")
    t1, t2 = st.tabs(["휴무 등록", "행사 등록"])
    with t1:
        c1, c2 = st.columns([2, 1])
        with c1: names_str = st.text_area("이름 (엔터 구분)", height=68)
        with c2: rng = st.date_input("기간", [], help="시작/종료일 선택")
        if names_str and len(rng) > 0:
            st.caption(f"{len(names_str.split())}명 선택됨")
        c3, c4 = st.columns(2)
        with c3: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="quick_type")
        with c4: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"])
        nte = st.text_input("비고")
        st.markdown('<div class="red-button">', unsafe_allow_html=True)
        if st.button("일괄 저장", type="primary", use_container_width=True):
            if names_str and len(rng) > 0:
                lst = [n.strip() for n in names_str.replace(',', '\n').split('\n') if n.strip()]
                # [안전장치] 에러 발생 시 멈춤
                try:
                    with st.spinner('저장 중입니다...'):
                        save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
                    st.toast("저장 완료!", icon="✅")
                    time.sleep(1)
                    st.rerun()
                except Exception:
                    st.error("🚨 저장 중 오류가 발생했습니다.")
                    st.code(traceback.format_exc())
            else: st.warning("이름과 기간을 입력해주세요.")
    with t2:
        c_e1, c_e2 = st.columns([2, 1])
        with c_e1:
            ed_list = st.date_input("행사 기간", [], help="시작/종료일")
            et = st.text_input("내용")
            if st.button("행사 저장", type="secondary"):
                if et and len(ed_list) > 0:
                    try:
                        with st.spinner('저장 중입니다...'):
                            s_d, e_d = ed_list[0], ed_list[1] if len(ed_list)>1 else ed_list[0]
                            for d in pd.date_range(s_d, e_d): add_company_event(d.strftime("%Y-%m-%d"), et)
                            st.cache_data.clear() 
                        st.success("저장됨"); st.rerun()
                    except Exception:
                        st.error("행사 저장 오류")
        st.divider()
        st.write("🗑️ **등록된 행사 목록**")
        events_df = load_data("company_events")
        if not events_df.empty:
            st.dataframe(events_df, use_container_width=True)
        else: st.info("등록된 행사가 없습니다.")

def render_driver_manage_tab():
    st.subheader("⚙️ 승무원 및 조(Group) 관리")
    tab_bulk, tab_change, tab_resign, tab_users = st.tabs(["➕ 승무원 등록", "🔄 조 변경", "👋 퇴사 처리", "🔐 관리자 계정"])
    with tab_bulk:
        c1, c2 = st.columns([3, 1])
        with c1: bulk_names = st.text_area("승무원 성명 목록 (엑셀 붙여넣기)", height=150)
        with c2: 
            selected_group = st.selectbox("소속 조", ["1조", "2조", "3조", "4조", "5조", "6조", "7조", "8조", "9조", "10조", "기타"])
            st.markdown("<br>", unsafe_allow_html=True)
            start_date = st.date_input("조 배정 시작일", get_kst_now().date())
            st.markdown('<div class="red-button">', unsafe_allow_html=True)
            if st.button("등록 실행", type="primary"):
                if bulk_names:
                    names = [n.strip() for n in bulk_names.replace(',', '\n').split('\n') if n.strip()]
                    cnt = 0
                    for name in names:
                        if ',' in name or '\t' in name: parts = name.replace('\t', ',').split(','); name = parts[0].strip()
                        if add_driver_with_group(name, selected_group, start_date.strftime("%Y-%m-%d")): cnt += 1
                    st.success(f"{cnt}명 등록 완료!"); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    with tab_change:
        st.info("💡 엑셀 등에서 이름을 복사해 붙여넣고, 변경할 조와 날짜를 선택하면 일괄 변경됩니다.")
        c1, c2 = st.columns([3, 1])
        with c1:
            change_names_str = st.text_area("대상 승무원 목록 (엔터로 구분)", height=200, key="change_names_input", placeholder="홍길동\n김철수\n이영희")
        with c2:
            target_grp = st.selectbox("이동할 조", ["1조", "2조", "3조", "4조", "5조", "6조", "7조", "8조", "9조", "10조", "기타"], key="new_grp_bulk")
            st.markdown("<br>", unsafe_allow_html=True)
            change_date = st.date_input("변경 기준일", get_kst_now().date(), key="eff_date_bulk")
            st.markdown('<div class="red-button">', unsafe_allow_html=True)
            if st.button("일괄 변경 적용", type="primary"):
                if change_names_str:
                    names_to_change = [n.strip() for n in change_names_str.replace(',', '\n').split('\n') if n.strip()]
                    all_drivers = load_data("drivers")
                    all_db_names = all_drivers['name'].astype(str).tolist() if not all_drivers.empty else []
                    valid_names = []
                    invalid_names = []
                    for name in names_to_change:
                        if name in all_db_names: valid_names.append(name)
                        else: invalid_names.append(name)
                    if invalid_names: st.error(f"❌ 다음 이름은 명단에 없어 제외됩니다: {', '.join(invalid_names)}")
                    if valid_names:
                        success_cnt = 0
                        for name in valid_names:
                            if add_driver_with_group(name, target_grp, change_date.strftime("%Y-%m-%d")): success_cnt += 1
                        st.success(f"✅ {success_cnt}명의 조를 '{target_grp}'로 변경했습니다.")
                        if success_cnt > 0: st.balloons()
                    else: st.warning("변경할 유효한 대상이 없습니다.")
                else: st.warning("이름을 입력해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)
    with tab_resign:
        drivers = load_data("drivers")
        if not drivers.empty and 'resigned_date' in drivers.columns:
            active_drivers = drivers[drivers['resigned_date'] == ""]
        else:
            active_drivers = pd.DataFrame()
        if not active_drivers.empty:
            st.info("💡 퇴사 처리를 하면 해당 날짜부터 근무 인원 집계 및 달력 표시에서 제외됩니다.")
            c_r1, c_r2 = st.columns(2)
            with c_r1: r_target = st.selectbox("퇴사자 선택", active_drivers['name'].tolist(), key="resign_dr")
            with c_r2: r_date = st.date_input("퇴사 일자", get_kst_now().date(), key="resign_date")
            st.markdown('<div class="red-button">', unsafe_allow_html=True)
            if st.button("퇴사 처리 실행", type="primary", key="btn_resign"):
                set_driver_resignation(r_target, r_date.strftime("%Y-%m-%d"))
                st.success(f"{r_target}님 퇴사 처리 완료"); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        else: st.info("등록된 승무원이 없습니다.")
    with tab_users:
        st.write("### 🔐 관리자 및 직원 계정 관리")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        with c1: new_id = st.text_input("새 아이디")
        with c2: new_pw = st.text_input("새 비밀번호", type="password")
        with c3: new_role = st.selectbox("권한", ["admin", "staff"], format_func=lambda x: "관리자" if x == "admin" else "직원")
        with c3: new_name = st.text_input("사용자 이름")
        with c4:
            st.markdown("<br>", unsafe_allow_html=True) 
            if st.button("계정 생성", type="primary"):
                if new_id and new_pw and new_name:
                    if add_user_account(new_id, new_pw, new_role, new_name):
                        st.success(f"계정 {new_id} 생성 완료"); st.rerun()
                    else: st.error("이미 존재하는 아이디입니다.")
                else: st.warning("모든 항목을 입력하세요.")
        st.divider()
        st.write("### 🔑 비밀번호 변경")
        users_df = load_data("users")
        if not users_df.empty:
            c_pw1, c_pw2, c_pw3 = st.columns([3, 3, 1])
            with c_pw1: target_user_pw = st.selectbox("대상 계정 선택", users_df['username'].tolist())
            with c_pw2: target_new_pw = st.text_input("변경할 비밀번호", type="password", key="chg_pw_input")
            with c_pw3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("비밀번호 변경", type="primary"):
                    if target_new_pw:
                        if update_user_password(target_user_pw, target_new_pw):
                            st.success(f"{target_user_pw}님의 비밀번호가 변경되었습니다.")
                        else: st.error("변경 실패")
                    else: st.warning("새 비밀번호를 입력하세요.")
        st.divider()
        st.write("📋 **등록된 계정 목록**")
        if not users_df.empty:
            for idx, row in users_df.iterrows():
                cc1, cc2, cc3, cc4, cc5 = st.columns([2, 2, 2, 2, 1])
                with cc1: st.write(f"**{row['username']}**")
                with cc2: st.write(row['name'])
                with cc3: st.write("관리자" if row['role']=='admin' else "직원")
                with cc4: st.write(row['created_at'])
                with cc5:
                    if row['username'] != 'admin':
                        if st.button("삭제", key=f"del_user_{row['username']}"):
                            delete_user_account(row['username'])
                            st.success("삭제됨"); st.rerun()
    st.divider()
    drivers = load_data("drivers")
    if not drivers.empty:
        search_dr = st.text_input("승무원 명부 검색")
        if search_dr and 'name' in drivers.columns: 
            drivers = drivers[drivers['name'].str.contains(search_dr)]
        if 'resigned_date' in drivers.columns:
            drivers['status'] = drivers['resigned_date'].apply(lambda x: f"퇴사 ({x})" if x else "재직")
            st.dataframe(drivers[['name', 'group_name', 'status']], hide_index=True, use_container_width=True, height=800)
        else:
            st.dataframe(drivers, use_container_width=True)
        with st.expander("🗑️ 승무원 삭제"):
            if 'name' in drivers.columns:
                del_target = st.selectbox("삭제 대상", drivers['name'].tolist(), key="del")
                if st.button("영구 삭제"): 
                    delete_driver(del_target)
                    st.rerun()

def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황")
    inject_custom_css()
    try:
        drivers = load_data("drivers")
        df = load_data("schedules")
        group_history_df = load_data("group_history")
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return
    if drivers.empty: 
        st.warning("승무원을 먼저 등록하세요.")
        return
    now = get_kst_now()
    if 'indiv_view_year' not in st.session_state: st.session_state.indiv_view_year = now.year
    if 'indiv_view_month' not in st.session_state: st.session_state.indiv_view_month = now.month
    c_sel, c_prev, c_date, c_next = st.columns([1.5, 0.5, 1, 0.5])
    with c_sel: target_name = st.selectbox("승무원 선택", drivers['name'].tolist())
    with c_prev:
        if st.button("◀", key="ind_prev", use_container_width=True):
            if st.session_state.indiv_view_month == 1:
                st.session_state.indiv_view_year -= 1; st.session_state.indiv_view_month = 12
            else: st.session_state.indiv_view_month -= 1
            st.rerun()
    with c_date: st.markdown(f"<h3 style='text-align:center; margin:0; padding-top:5px;'>{st.session_state.indiv_view_year}년 {st.session_state.indiv_view_month}월</h3>", unsafe_allow_html=True)
    with c_next:
        if st.button("▶", key="ind_next", use_container_width=True):
            if st.session_state.indiv_view_month == 12:
                st.session_state.indiv_view_year += 1; st.session_state.indiv_view_month = 1
            else: st.session_state.indiv_view_month += 1
            st.rerun()
    target_year = st.session_state.indiv_view_year
    target_month = st.session_state.indiv_view_month
    
    # Dictionary 변환 (개별 화면도 최적화)
    history_dict = {}
    if not group_history_df.empty and 'driver_name' in group_history_df.columns:
        for idx, row in group_history_df.iterrows():
            d_name = row['driver_name']
            if d_name not in history_dict: history_dict[d_name] = []
            history_dict[d_name].append((row['start_date'], row['group_name']))
        for d_name in history_dict:
            history_dict[d_name].sort(key=lambda x: x[0], reverse=True)

    if target_name:
        st.markdown(f"### 🚍 **{target_name}**"); st.divider()
        filter_ym = f"{target_year}-{target_month:02d}"
        my_schedules = pd.DataFrame()
        if not df.empty and 'name' in df.columns and 'date' in df.columns:
            my_schedules = df[(df['name'] == target_name) & (df['date'].astype(str).str.startswith(filter_ym))]
        cal = calendar.monthcalendar(target_year, target_month)
        cols = st.columns(7)
        for i, w in enumerate(WEEKDAY_KOREAN):
            cols[i].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
        for week in cal:
            cols = st.columns(7)
            for i, day in enumerate(week):
                with cols[i]:
                    if day == 0: st.write("")
                    else:
                        d_str = f"{target_year}-{target_month:02d}-{day:02d}"
                        eff_grp = get_group_from_dict(history_dict, target_name, d_str)
                        auto = calculate_auto_shift(eff_grp, d_str)
                        d_sch = pd.DataFrame()
                        if not my_schedules.empty: d_sch = my_schedules[my_schedules['date'] == d_str]
                        cell_bg = "transparent"
                        text_color = "black"
                        sub_text = ""
                        if not d_sch.empty:
                            r = d_sch.iloc[0]
                            t = r['type']
                            if t == "휴무": cell_bg = "#ffc9c9"; text_color = "#c92a2a"; sub_text = "휴무"
                            elif t in ["교육", "경조사", "병가", "휴직"]: cell_bg = "#ffe8cc"; text_color = "#d9480f"; sub_text = t
                            else: cell_bg = "#f1f3f5"; sub_text = t
                        elif auto:
                            if auto == "오전": cell_bg = "#e7f5ff"; text_color = "#1864ab"; sub_text = f"오전 ({eff_grp})"
                            elif auto == "오후": cell_bg = "#fff4e6"; text_color = "#e67700"; sub_text = f"오후 ({eff_grp})"
                            elif auto == "휴무": cell_bg = "#f8f9fa"; text_color = "#868e96"; sub_text = f"휴무 ({eff_grp})"
                        st.markdown(f"""
                        <div style='background-color:{cell_bg}; border:1px solid #dee2e6; border-radius:5px; padding:5px; min-height:80px; display:flex; flex-direction:column; justify-content:space-between; height:100%;'>
                            <div style='font-weight:bold; font-size:14px; color:#333;'>{day}</div>
                            <div style='text-align:center; font-weight:bold; font-size:13px; color:{text_color}; margin-top:5px;'>{sub_text}</div>
                        </div>""", unsafe_allow_html=True)

def render_view_manage_tab():
    st.subheader("📊 조회 및 관리")
    df = load_data("schedules")
    if df.empty: st.info("데이터 없음"); return
    if 'date' not in df.columns: st.error("DB 형식 오류: date 컬럼 없음"); return
    df['display_date'] = df['date']
    with st.expander("🔎 검색", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1: sn = st.text_input("이름", key="search_name_admin")
        with c2: sd = st.date_input("기간", [], key="search_date_admin")
        type_options = ["전체"]
        if 'type' in df.columns: type_options += list(df['type'].unique())
        with c3: stp = st.selectbox("종류", type_options, key="search_type_admin")
    if sn and 'name' in df.columns: df = df[df['name'].str.contains(sn)]
    if len(sd) == 2: df = df[(df['date'] >= sd[0].strftime("%Y-%m-%d")) & (df['date'] <= sd[1].strftime("%Y-%m-%d"))]
    if stp != "전체" and 'type' in df.columns: df = df[df['type'] == stp]
    is_admin = st.session_state.get('auth_status') == 'admin'
    if is_admin:
        st.info("⚠️ 데이터 수정/삭제는 구글 시트에서 직접 하시는 것이 가장 빠르고 정확합니다.")
        st.dataframe(df, use_container_width=True, height=800)
    else:
        disp_cols = ['date', 'name', 'type', 'note']
        valid_cols = [c for c in disp_cols if c in df.columns]
        st.dataframe(df[valid_cols], use_container_width=True, height=1000)

def render_public_search_tab():
    render_view_manage_tab() 

def main():
    st.set_page_config(page_title="우진교통 승무원 휴무 관리", layout="wide")
    inject_custom_css()
    if 'auth_status' not in st.session_state: st.session_state['auth_status'] = None
    if st.session_state['auth_status'] is None:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.title("우진교통 승무원 휴무 관리")
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            if st.button("로그인", type="primary", use_container_width=True):
                user = login_user(uid, upw)
                if user:
                    role, name = user
                    st.session_state['auth_status'] = role
                    st.session_state['user_name'] = name
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 잘못되었습니다.")
            st.markdown('</div>', unsafe_allow_html=True)
        return
    c1, c2 = st.columns([8, 1])
    with c1: st.title(f"우진교통 승무원 휴무 관리 ({st.session_state.get('user_name', '사용자')}님)")
    with c2: 
        if st.button("로그아웃"): st.session_state['auth_status'] = None; st.rerun()
    if st.session_state['auth_status'] == 'admin':
        t1, t2, t3, t4, t5, t6 = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력", "⚙️ 승무원", "📊 조회", "🔧 시스템 로그"])
        with t1: render_calendar_tab()
        with t2: render_individual_calendar_tab()
        with t3: render_input_tab()
        with t4: render_driver_manage_tab()
        with t5: render_view_manage_tab()
        with t6: render_log_tab()
    else:
        t1, t2, t3 = st.tabs(["📅 전체 현황", "👤 개인별", "📊 조회"])
        with t1: render_calendar_tab()
        with t2: render_individual_calendar_tab()
        with t3: render_public_search_tab()

if __name__ == '__main__':
    main()
