import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import time
import holidays
import re

# ==========================================
# 1. 전역 상수 및 공통 설정
# ==========================================
WEEKDAY_KOREAN = ["월", "화", "수", "목", "금", "토", "일"]
SORT_ORDER = {"휴무": 1, "교육": 2, "경조사": 3, "징계": 4, "당일 해지": 5, "기타": 6, "휴직": 7, "병가": 8}
kr_holidays = holidays.KR()

def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

def make_hash(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

def get_type_color(type_name):
    colors = { 
        "휴무": "#00592D", "교육": "#8c6b4a", "경조사": "#1F3994", 
        "징계": "#000000", "당일 해지": "#8B0000", "병가": "#A52A2A", 
        "휴직": "#D2691E", "육아휴직": "#D2691E", "기타": "#363636",
        "실제근무_본인": "#1e88e5", # 파랑
        "실제근무_대운": "#8e24aa",  # 보라
        "감차휴무": "#00592D" # 녹색
    }
    return colors.get(type_name, "#546E7A")

def inject_custom_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
        div[data-testid="column"] { padding: 0px !important; gap: 0px !important; }
        .horizontal-scroll-container { display: flex; overflow-x: auto; gap: 0px; padding-bottom: 15px; width: 100%; }
        .calendar-day-box { border: 1px solid #e9ecef; min-height: 200px; padding: 0; background-color: white; display: flex; flex-direction: column; height: auto !important; }
        .calendar-day-box-horiz { flex: 0 0 90px; } 
        .calendar-day-box-grid { width: 100%; margin: 2px; }
        .horizontal-scroll-container::-webkit-scrollbar { height: 8px; }
        .horizontal-scroll-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        .horizontal-scroll-container::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
        .daily-stats-box { background-color: #f1f3f5; border-bottom: 1px solid #e9ecef; font-size: 11px; text-align: center; padding: 3px 0; color: #495057; font-weight: bold; white-space: nowrap; }
        .group-info-box { font-size: 10px; padding: 2px 4px; background-color: #fff; border-bottom: 1px solid #f1f3f5; line-height: 1.2; font-weight: bold; }
        .event-container { height: 46px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; border-bottom: 1px solid #f1f3f5; padding: 2px 1px; background-color: #fff; }
        .event-container::-webkit-scrollbar { display: none; }
        .day-header { display: flex; flex-direction: column; padding-top: 4px; padding-bottom: 4px; gap: 1px; justify-content: center; background-color: transparent; border-bottom: 1px solid #eee; }
        .schedule-bar { color: white; padding: 0 2px; margin-bottom: 1px; line-height: 1.1; text-align: center; cursor: help; font-size: 11px; height: 34px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; border-top: none; border-bottom: none; }
        .bar-start { border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0; border-bottom-right-radius: 0; margin-right: -10px !important; margin-left: 2px; position: relative; z-index: 2; }
        .bar-mid { border-radius: 0; border-left: none; border-right: none; margin-left: -10px !important; margin-right: -10px !important; position: relative; z-index: 1; }
        .bar-end { border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-top-left-radius: 0; border-bottom-left-radius: 0; margin-left: -10px !important; margin-right: 2px; position: relative; z-index: 2; }
        .bar-single { border-radius: 4px; margin: 0 2px 1px 2px; z-index: 3; }
        .schedule-spacer { height: 34px; margin-bottom: 1px; background-color: transparent; }
        button[kind="primary"], div[data-testid="stButton"] button { background-color: #00592D !important; border-color: #00592D !important; color: white !important; }
        button[kind="primary"]:hover, div[data-testid="stButton"] button:hover { background-color: #004d26 !important; border-color: #004d26 !important; color: white !important; }
        @media (max-width: 640px) { h1 { font-size: 1.6rem !important; } .mobile-font { font-size: 10px !important; } .mobile-header { font-size: 11px !important; } }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DB 연결 및 데이터 로드 (영구 캐싱)
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
        df = pd.DataFrame(data, columns=headers)
        if sheet_name != 'users' and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=['date']) 
        if 'name' in df.columns:
            df['name'] = df['name'].astype(str).str.strip()
        return df
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

def clear_cache_after_save():
    st.cache_data.clear()

# ==========================================
# 3. 데이터 저장 및 관리 함수 (누락된 함수 복구)
# ==========================================
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
    if 'action_logs' not in st.session_state:
        st.session_state['action_logs'] = []
    st.session_state['action_logs'].insert(0, log_entry)

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

def save_work_history(df_new):
    sh = get_db_connection()
    try:
        ws = sh.worksheet("work_history")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="work_history", rows=1000, cols=10)
        ws.append_row(['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at'])

    existing_data = ws.get_all_values()
    df_old = pd.DataFrame()
    if len(existing_data) > 1:
        headers = existing_data.pop(0)
        df_old = pd.DataFrame(existing_data, columns=headers)
    
    if df_old.empty:
        df_final = df_new
    else:
        required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at']
        for c in required_cols:
            if c not in df_new.columns: df_new[c] = ""
            if c not in df_old.columns: df_old[c] = ""
        df_new = df_new[required_cols]
        df_old = df_old[required_cols]
        df_combined = pd.concat([df_old, df_new])
        df_final = df_combined.drop_duplicates(subset=['date', 'name', 'shift'], keep='last')
        
    df_final = df_final.sort_values(by=['date', 'name'])
    
    ws.clear()
    ws.append_row(['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at'])
    
    data_to_write = df_final.fillna("").astype(str).values.tolist()
    if data_to_write:
        ws.append_rows(data_to_write)
        
    clear_cache_after_save()
    return len(df_new)

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
    
def add_reduction_rule(start, end, route, seq, cond):
    sh = get_db_connection()
    try:
        ws = sh.worksheet("reduction_rules")
    except:
        ws = sh.add_worksheet(title="reduction_rules", rows=100, cols=5)
        ws.append_row(['start_date', 'end_date', 'route', 'sequence', 'condition'])
    ws.append_row([str(start), str(end), str(route), str(seq), cond])
    clear_cache_after_save()

# ==========================================
# 4. 날짜 및 스케줄 계산 로직 (감차 포함)
# ==========================================
def is_holiday(date_obj):
    return date_obj in kr_holidays

def is_holiday_or_weekend(date_obj):
    return date_obj.weekday() >= 5 or date_obj in kr_holidays

def clean_driver_name(name):
    if pd.isna(name): return "" 
    s = str(name).strip()
    if s.lower() == "nan" or s == "": return ""
    s = re.sub(r'\(.*?\)', '', s) 
    s = s.replace(" ", "").strip()
    return s

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

def get_reduction_rules():
    df = load_data("reduction_rules")
    rules = []
    if not df.empty and 'start_date' in df.columns:
        for _, row in df.iterrows():
            rules.append({
                'start': row['start_date'],
                'end': row['end_date'],
                'route': str(row['route']).strip(),
                'seq': str(row['sequence']).strip(),
                'condition': row['condition']
            })
    return rules

def is_reduction_target(date_str, route, seq, rules):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except: return False
    is_holi = is_holiday_or_weekend(d)
    for r in rules:
        if r['start'] <= date_str <= r['end']:
            if r['route'] == str(route).strip() and r['seq'] == str(seq).strip():
                if r['condition'] == 'Always': return True
                if r['condition'] == 'Weekend/Holiday' and is_holi: return True
    return False

# ==========================================
# 5. 로그인 및 사용자 관리 (기존 유지)
# ==========================================
def login_user(username, password):
    df = load_data("users")
    if df.empty: return None
    pw_hash = make_hash(password)
    if 'username' not in df.columns: return None
    df['username'] = df['username'].astype(str)
    user = df[(df['username'] == username) & (df['password'] == pw_hash)]
    if not user.empty:
        return user.iloc[0]['role'], user.iloc[0]['name']
    return None

def log_login_access(username, name):
    try:
        sh = get_db_connection()
        try:
            ws = sh.worksheet("access_logs")
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title="access_logs", rows=1000, cols=4)
            ws.append_row(["timestamp", "username", "name", "status"])
        timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([timestamp, username, name, "Login Success"])
        st.cache_data.clear()
    except: pass

def parse_roster_excel(file):
    df_raw = pd.read_excel(file, header=None)
    date_rows = []
    for idx, row in df_raw.iterrows():
        val = str(row[0])
        if "202" in val or "년" in val:
            try:
                if pd.notnull(df_raw.iloc[idx, 3]) and pd.notnull(df_raw.iloc[idx, 5]):
                    date_rows.append(idx)
            except: pass
            
    extracted_data = []
    
    for start_row in date_rows:
        try:
            year = int(str(df_raw.iloc[start_row, 0]).replace("년","").strip())
            month = int(str(df_raw.iloc[start_row, 3]).replace("월","").strip())
            day = int(str(df_raw.iloc[start_row, 5]).replace("일","").strip())
            current_date = datetime(year, month, day).strftime("%Y-%m-%d")
        except: continue 

        cols_map = [
            {'route':1, 'seq':2, 'car':3, 'am_fix':4, 'am_sub':5, 'pm_fix':6, 'pm_sub':7}, # Left
            {'route':9, 'seq':10, 'car':11, 'am_fix':12, 'am_sub':13, 'pm_fix':14, 'pm_sub':15} # Right
        ]
        
        for side in cols_map:
            last_route = None
            for r_offset in range(3, 75): 
                curr_idx = start_row + r_offset
                if curr_idx >= len(df_raw): break
                
                raw_route = df_raw.iloc[curr_idx, side['route']]
                if pd.notnull(raw_route) and str(raw_route).strip() != "":
                    last_route = str(raw_route).strip()
                current_route = last_route if last_route else ""

                raw_seq = df_raw.iloc[curr_idx, side['seq']]
                raw_car = df_raw.iloc[curr_idx, side['car']]
                
                current_seq = str(raw_seq).strip() if pd.notnull(raw_seq) else ""
                
                try:
                    raw_car_str = str(raw_car).strip()
                    digits_only = re.sub(r'[^0-9]', '', raw_car_str)
                    car_num = int(digits_only)
                    is_valid_car = (5001 <= car_num <= 5300)
                    current_car = str(car_num)
                except:
                    is_valid_car = False
                    current_car = ""

                if not (current_route and current_seq and is_valid_car):
                    continue
                
                am_fix = clean_driver_name(df_raw.iloc[curr_idx, side['am_fix']])
                am_sub = clean_driver_name(df_raw.iloc[curr_idx, side['am_sub']])
                am_final = am_sub if am_sub else am_fix
                
                pm_fix = clean_driver_name(df_raw.iloc[curr_idx, side['pm_fix']])
                pm_sub = clean_driver_name(df_raw.iloc[curr_idx, side['pm_sub']])
                pm_final = pm_sub if pm_sub else pm_fix
                
                if am_final: 
                    extracted_data.append({
                        'date': current_date, 'name': am_final, 'shift': '오전', 
                        'route': current_route, 'seq': current_seq, 'car': current_car, 
                        'is_sub': bool(am_sub), 'orig_fix': am_fix
                    })
                
                if pm_final:
                    extracted_data.append({
                        'date': current_date, 'name': pm_final, 'shift': '오후', 
                        'route': current_route, 'seq': current_seq, 'car': current_car, 
                        'is_sub': bool(pm_sub), 'orig_fix': pm_fix
                    })
    return pd.DataFrame(extracted_data)
