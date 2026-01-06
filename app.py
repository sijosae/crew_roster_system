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
import holidays

# ==========================================
# 0. 로그 및 초기화
# ==========================================
def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

if 'system_logs' not in st.session_state:
    st.session_state['system_logs'] = []

if 'last_error_msg' not in st.session_state:
    st.session_state['last_error_msg'] = None

if 'action_logs' not in st.session_state:
    st.session_state['action_logs'] = []

def add_log(msg, ids=None, sheet_name=None, level="INFO"):
    timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "time": timestamp,
        "msg": msg,
        "level": level,
        "ids": ids if ids else [],
        "sheet": sheet_name,
        "status": "active"
    }
    st.session_state['action_logs'].insert(0, log_entry)

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
# 2. 실행 취소 (Undo) 로직
# ==========================================
def delete_rows_by_ids(sheet_name, id_list):
    if not id_list: return False
    sh = get_db_connection()
    ws = sh.worksheet(sheet_name)
    col_values = ws.col_values(1) 
    rows_to_delete = []
    for target_id in id_list:
        try:
            row_idx = col_values.index(target_id) + 1
            rows_to_delete.append(row_idx)
        except ValueError: continue
    rows_to_delete.sort(reverse=True)
    for r_idx in rows_to_delete:
        ws.delete_rows(r_idx)
    clear_cache_after_save()
    return True

# ==========================================
# 3. 인증 및 계정
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
# 4. 데이터 저장
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

def save_range_batch(name_list, start, end, type, shift, note):
    dates = pd.date_range(start, end)
    now_kst = get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    base_id = now_kst.strftime("%y%m%d%H%M") 
    
    rows_to_add = []
    generated_ids = [] 
    count = 0
    for name in name_list:
        for d in dates:
            d_str = d.strftime("%Y-%m-%d")
            row_id = f"{base_id}{count:02d}"
            generated_ids.append(row_id)
            rows_to_add.append([row_id, name, d_str, type, note, created_at, shift])
            count += 1
            
    if rows_to_add:
        sh = get_db_connection()
        ws = sh.worksheet("schedules")
        ws.append_rows(rows_to_add)
        clear_cache_after_save()
        
    return len(rows_to_add), generated_ids

def add_company_event(date, title):
    sh = get_db_connection()
    ws = sh.worksheet("company_events")
    now_kst = get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d")
    row_id = now_kst.strftime("%y%m%d%H%M%S")
    ws.append_row([row_id, date, title, created_at])
    clear_cache_after_save()
    return row_id

# ==========================================
# 5. 로직 및 계산
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

# [수정] 스타벅스 & 프로페셔널 딥 컬러 테마
def get_type_color(type_name):
    colors = { 
        "휴무": "#00592D",      # 스타벅스 그린
        "교육": "#8c6b4a",      # 딥 로스트 브라운
        "경조사": "#1F3994",    # 딥 네이비
        "징계": "#000000",      # 완전 검정
        "당일 해지": "#8B0000", # 다크 레드
        "병가": "#A52A2A",      # 브라운 레드
        "휴직": "#D2691E",      # 초콜릿
        "육아휴직": "#D2691E", 
        "기타": "#363636"       # 차콜 그레이
    }
    return colors.get(type_name, "#546E7A")

def get_off_groups(date_str):
    ref = datetime(2025, 12, 1)
    target = datetime.strptime(date_str, "%Y-%m-%d")
    cycle = (target - ref).days % 5
    return [("1,6조", ["1조", "6조"]), ("2,7조", ["2조", "7조"]), ("3,8조", ["3조", "8조"]), ("4,9조", ["4조", "9조"]), ("5,10조", ["5조", "10조"])][cycle]

kr_holidays = holidays.KR()

def is_holiday(date_obj):
    return date_obj in kr_holidays

def get_daily_shift_summary(date_str):
    am, pm = [], []
    off_from_am, off_from_pm = [], []
    prev_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    for i in range(1, 11):
        grp_name = f"{i}조"
        s = calculate_auto_shift(grp_name, date_str)
        if s == "오전": am.append(str(i))
        elif s == "오후": pm.append(str(i))
        else:
            prev_s = calculate_auto_shift(grp_name, prev_date)
            if prev_s == "오전": off_from_am.append(str(i)) 
            else: off_from_pm.append(str(i))
    line1 = f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:1px;'><span style='color:#1c7ed6; font-weight:bold;'>오전: {','.join(am)}</span><span style='color:#868e96; font-size:0.85em; font-weight:bold;'>휴무: {','.join(off_from_am)}</span></div>"
    line2 = f"<div style='display:flex; justify-content:space-between; align-items:center;'><span style='color:#d9480f; font-weight:bold;'>오후: {','.join(pm)}</span><span style='color:#868e96; font-size:0.85em; font-weight:bold;'>휴무: {','.join(off_from_pm)}</span></div>"
    return line1 + line2

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
    active_drivers_list = []
    
    if not all_drivers_df.empty:
        has_resign_col = 'resigned_date' in all_drivers_df.columns
        for _, dr in all_drivers_df.iterrows():
            is_active = True
            if has_resign_col:
                r_date = str(dr['resigned_date']).strip()
                if r_date and date_str > r_date:
                    is_active = False
            if is_active:
                active_drivers_list.append(dr['name'])
    
    total = len(active_drivers_list)
    am_cnt, pm_cnt, off_cnt = 0, 0, 0
    
    if not today_schedules_df.empty and 'shift' not in today_schedules_df.columns:
        today_schedules_df['shift'] = '자동'

    manual_map = {}
    if not today_schedules_df.empty:
        for _, row in today_schedules_df.iterrows():
            manual_map[row['name']] = (row['type'], row.get('shift', '자동'))
    
    for name in active_drivers_list:
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
# 6. 화면 렌더링
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
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
        
        /* [수정] 테두리 3px 진한 검정 회색 (#222) 적용 */
        .schedule-bar { color: white; padding: 0 2px; margin-bottom: 1px; line-height: 1.1; text-align: center; cursor: help; font-size: 11px; height: 34px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; border-top: none; border-bottom: none; }
        .bar-start { border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0; border-bottom-right-radius: 0; margin-right: -10px !important; margin-left:
