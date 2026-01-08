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
import re
import io

# ==========================================
# 0. 전역 상수 및 콜백 함수 (최상단 배치)
# ==========================================
WEEKDAY_KOREAN = ["월", "화", "수", "목", "금", "토", "일"]
SORT_ORDER = {"휴무": 1, "교육": 2, "경조사": 3, "징계": 4, "당일 해지": 5, "기타": 6, "휴직": 7, "병가": 8}

def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

# [핵심] 버튼 클릭 시 Session State와 Selectbox Key를 동시에 강제 동기화
def prev_cal_callback():
    new_m = st.session_state.view_month - 1
    new_y = st.session_state.view_year
    if new_m < 1:
        new_m = 12
        new_y -= 1
    st.session_state.view_month = new_m
    st.session_state.view_year = new_y
    st.session_state.sb_view_month = new_m 
    st.session_state.sb_view_year = new_y

def next_cal_callback():
    new_m = st.session_state.view_month + 1
    new_y = st.session_state.view_year
    if new_m > 12:
        new_m = 1
        new_y += 1
    st.session_state.view_month = new_m
    st.session_state.view_year = new_y
    st.session_state.sb_view_month = new_m
    st.session_state.sb_view_year = new_y

def prev_month_indiv():
    new_m = st.session_state.indiv_view_month - 1
    new_y = st.session_state.indiv_view_year
    if new_m < 1:
        new_m = 12
        new_y -= 1
    st.session_state.indiv_view_month = new_m
    st.session_state.indiv_view_year = new_y
    st.session_state.sb_ind_month = new_m
    st.session_state.sb_ind_year = new_y

def next_month_indiv():
    new_m = st.session_state.indiv_view_month + 1
    new_y = st.session_state.indiv_view_year
    if new_m > 12:
        new_m = 1
        new_y += 1
    st.session_state.indiv_view_month = new_m
    st.session_state.indiv_view_year = new_y
    st.session_state.sb_ind_month = new_m
    st.session_state.sb_ind_year = new_y

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
        df = pd.DataFrame(data, columns=headers)
        # [중요] 날짜 컬럼 정규화 (YYYY-MM-DD)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=['date']) 
        return df
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

def clear_cache_after_save():
    st.cache_data.clear()

# ==========================================
# 2. 실행 취소 및 계정 관리
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

def make_hash(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

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
# 3. 데이터 저장 로직
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
# 4. [모듈] 배차일지 분석 및 감차(Reduction) 엔진
# ==========================================
kr_holidays = holidays.KR()

def is_holiday_or_weekend(date_obj):
    return date_obj.weekday() >= 5 or date_obj in kr_holidays

def clean_driver_name(name):
    if pd.isna(name): return "" 
    s = str(name).strip()
    if s.lower() == "nan" or s == "": return ""
    s = re.sub(r'\(.*?\)', '', s) 
    s = s.replace(" ", "").strip()
    return s

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
            if r['route'] == route and r['seq'] == seq:
                if r['condition'] == 'Always': return True
                if r['condition'] == 'Weekend/Holiday' and is_holi: return True
    return False

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
# 5. 로직 및 계산
# ==========================================
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

def get_type_color(type_name):
    colors = { 
        "휴무": "#00592D", "교육": "#8c6b4a", "경조사": "#1F3994", 
        "징계": "#000000", "당일 해지": "#8B0000", "병가": "#A52A2A", 
        "휴직": "#D2691E", "육아휴직": "#D2691E", "기타": "#363636",
        "실제근무_본인": "#1e88e5", # 파랑
        "실제근무_대운": "#8e24aa",  # 보라
        "근무_오전": "#1e88e5", # 파랑
        "근무_오후": "#e53935" # 빨강
    }
    return colors.get(type_name, "#546E7A")

def get_off_groups(date_str):
    ref = datetime(2025, 12, 1)
    target = datetime.strptime(date_str, "%Y-%m-%d")
    cycle = (target - ref).days % 5
    return [("1,6조", ["1조", "6조"]), ("2,7조", ["2조", "7조"]), ("3,8조", ["3조", "8조"]), ("4,9조", ["4조", "9조"]), ("5,10조", ["5조", "10조"])][cycle]

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
                if r_date and date_str > r_date: is_active = False
            if is_active: active_drivers_list.append(dr['name'])
    
    total = len(active_drivers_list)
    am_cnt, pm_cnt, off_cnt = 0, 0, 0
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
            if grp: final_shift = calculate_auto_shift(grp, date_str)
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
        if (p_name, prev_d) in full_schedule_map and full_schedule_map[(p_name, prev_d)] == p_type: start_date -= timedelta(days=1)
        else: break
    while True:
        next_d = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
        if (p_name, next_d) in full_schedule_map and full_schedule_map[(p_name, next_d)] == p_type: end_date += timedelta(days=1)
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
        
        /* 박스 그림자 적용 (테두리 두께로 인한 밀림 방지) */
        .calendar-day-box { 
            border: 1px solid #e9ecef; 
            min-height: 200px; 
            padding: 0; 
            background-color: white; 
            display: flex; 
            flex-direction: column; 
            height: auto !important; 
        }
        
        .calendar-day-box-horiz { flex: 0 0 90px; } 
        .calendar-day-box-grid { width: 100%; margin: 2px; }
        
        .horizontal-scroll-container::-webkit-scrollbar { height: 8px; }
        .horizontal-scroll-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        .horizontal-scroll-container::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
        .horizontal-scroll-container::-webkit-scrollbar-thumb:hover { background: #aaa; }
        .daily-stats-box { background-color: #f1f3f5; border-bottom: 1px solid #e9ecef; font-size: 11px; text-align: center; padding: 3px 0; color: #495057; font-weight: bold; white-space: nowrap; }
        .group-info-box { font-size: 10px; padding: 2px 4px; background-color: transparent; border-bottom: 1px solid #f1f3f5; line-height: 1.2; font-weight: bold; }
        .event-container { height: 46px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; border-bottom: 1px solid #f1f3f5; padding: 2px 1px; background-color: transparent; }
        .event-container::-webkit-scrollbar { display: none; }
        .day-header { display: flex; flex-direction: column; padding-top: 4px; padding-bottom: 4px; gap: 1px; justify-content: center; background-color: transparent; border-bottom: 1px solid #eee; }
        
        .schedule-bar { color: white; padding: 0 2px; margin-bottom: 1px; line-height: 1.1; text-align: center; cursor: help; font-size: 11px; height: 34px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; border-top: none; border-bottom: none; }
        .bar-start { border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0; border-bottom-right-radius: 0; margin-right: -10px !important; margin-left: 2px; position: relative; z-index: 2; }
        .bar-mid { border-radius: 0; border-left: none; border-right: none; margin-left: -10px !important; margin-right: -10px !important; position: relative; z-index: 1; }
        .bar-end { border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-top-left-radius: 0; border-bottom-left-radius: 0; margin-left: -10px !important; margin-right: 2px; position: relative; z-index: 2; }
        .bar-single { border-radius: 4px; margin: 0 2px 1px 2px; z-index: 3; }
        .schedule-spacer { height: 34px; margin-bottom: 1px; background-color: transparent; }

        /* 로그인 버튼 - 초강력 CSS 우선순위 적용 */
        button[kind="primary"], div[data-testid="stButton"] button {
            background-color: #00592D !important;
            border-color: #00592D !important;
            color: white !important;
        }
        button[kind="primary"]:hover, div[data-testid="stButton"] button:hover {
            background-color: #004d26 !important;
            border-color: #004d26 !important;
            color: white !important;
        }
        
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
        c1, c2 = st.columns(2)
        with c1: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="quick_type")
        with c2: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="quick_shift")
        nte = st.text_input("비고", key="quick_note")
        
        if st.button("승무원 일정 저장", type="primary", use_container_width=True):
            if names_str and len(rng) > 0:
                lst = [n.strip() for n in names_str.replace(',', '\n').split('\n') if n.strip()]
                try:
                    with st.spinner('저장 중입니다...'):
                        count, ids = save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
                    st.toast("✅ 저장 완료!", icon="🔄")
                    add_log(f"입력 성공: {len(lst)}명", ids=ids, sheet_name="schedules")
                    time.sleep(0.7); st.rerun()
                except Exception as e: st.error("🚨 저장 중 오류 발생!")
            else: st.warning("이름과 기간을 입력해주세요.")
    with tab2:
        st.write("회사 주요 행사를 달력 상단에 표시합니다.")
        ed_list = st.date_input("행사 기간", [], help="시작/종료일", key="quick_event_range")
        et = st.text_input("행사 내용", key="quick_event_title")
        if st.button("회사 행사 저장", type="primary", use_container_width=True, key="quick_event_save"):
            if et and len(ed_list) > 0:
                try:
                    with st.spinner('저장 중입니다...'):
                        for d in pd.date_range(ed_list[0], ed_list[-1]): add_company_event(d.strftime("%Y-%m-%d"), et)
                        st.cache_data.clear()
                    st.toast("✅ 행사 저장 완료!", icon="🔄")
                    add_log(f"행사 등록: {et}", sheet_name="company_events")
                    time.sleep(0.7); st.rerun()
                except Exception: st.error("오류 발생")
            else: st.warning("기간과 내용을 입력해주세요.")

def render_log_tab():
    st.subheader("🔧 시스템 로그 및 실행 취소")
    t_act, t_acc = st.tabs(["📋 작업 로그", "👥 접속 이력"])
    with t_act:
        if st.button("🗑️ 로그 비우기"): st.session_state['action_logs'] = []; st.rerun()
        st.divider()
        for i, log in enumerate(st.session_state['action_logs']):
            c1, c2, c3 = st.columns([1, 4, 1])
            with c1: st.write(log['time'])
            with c2: st.write(f"{log['msg']}")
            with c3:
                if log['status'] == 'active' and log.get('ids'):
                    if st.button("↩️ 실행 취소", key=f"undo_{i}"):
                        delete_rows_by_ids(log['sheet'], log['ids'])
                        log['status'] = 'canceled'; st.rerun()
    with t_acc:
        try:
            df_acc = load_data("access_logs")
            if not df_acc.empty: st.dataframe(df_acc.sort_values(by='timestamp', ascending=False), use_container_width=True)
            else: st.info("접속 기록이 없습니다.")
        except: st.warning("로그 없음")

def render_calendar_tab():
    if st.session_state.get('last_error_msg'): st.error("오류 발생"); st.code(st.session_state['last_error_msg'])
    try: _render_calendar_tab_unsafe()
    except Exception: st.error("캘린더 렌더링 오류"); st.code(traceback.format_exc())

def _render_calendar_tab_unsafe():
    c_title, c_legend, c_view = st.columns([1, 1.5, 0.8])
    with c_title:
        st.markdown("### 📅 월간 휴무 신청 현황")
    with c_legend:
        types = ["휴무", "교육", "경조사", "징계", "당일 해지", "병가", "휴직", "기타"]
        legend_html = "<div style='display:flex; flex-wrap:wrap; gap:5px; align-items:center; height:100%; margin-top:10px;'>"
        for t in types:
            c = get_type_color(t)
            t_label = t
            legend_html += f"<span style='background:{c}; color:white; border:1px solid #333; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:bold;'>{t_label}</span>"
        legend_html += "</div>"
        st.markdown(legend_html, unsafe_allow_html=True)
    with c_view:
        view_mode = st.radio("보기", ["가로 스크롤", "달력"], horizontal=True, label_visibility="collapsed")
    
    inject_custom_css()
    
    now = get_kst_now()
    if 'view_year' not in st.session_state: st.session_state.view_year = now.year
    if 'view_month' not in st.session_state: st.session_state.view_month = now.month
    if 'sb_view_year' not in st.session_state: st.session_state.sb_view_year = now.year
    if 'sb_view_month' not in st.session_state: st.session_state.sb_view_month = now.month
    
    c1, c2, c3, c4, c5, c6, c7 = st.columns([0.3, 0.7, 0.3, 0.7, 0.4, 0.4, 1.2])
    with c1: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c2: st.selectbox("년도", range(2023, now.year + 3), key='sb_view_year', label_visibility="collapsed")
    if st.session_state.sb_view_year != st.session_state.view_year:
        st.session_state.view_year = st.session_state.sb_view_year
        st.rerun()

    with c3: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c4: st.selectbox("월", range(1, 13), key='sb_view_month', label_visibility="collapsed")
    if st.session_state.sb_view_month != st.session_state.view_month:
        st.session_state.view_month = st.session_state.sb_view_month
        st.rerun()

    with c5: st.button("◀", key="prev_cal_btn", on_click=prev_cal_callback)
    with c6: st.button("▶", key="next_cal_btn", on_click=next_cal_callback)
    with c7:
        if st.session_state.get('auth_status') == 'admin':
            if st.button("➕ 빠른 입력", type="primary", use_container_width=True): show_input_dialog()
            
    st.divider()
    
    year, month = st.session_state.view_year, st.session_state.view_month
    
    # [수정] 오직 Schedules DB만 로드 (Work History 제외)
    df_schedules = load_data("schedules")
    if df_schedules.empty: df_schedules = pd.DataFrame(columns=['date','name','type','note'])
    
    # 날짜 필터링
    df_month = df_schedules[df_schedules['date'].astype(str).str.startswith(f"{year}-{month:02d}")]
    
    df_events = load_data("company_events")
    df_events_month = df_events[df_events['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df_events.empty else pd.DataFrame()
    
    all_drivers = load_data("drivers")
    group_history_df = load_data("group_history")
    history_dict = {}
    if not group_history_df.empty:
        for _, row in group_history_df.iterrows():
            if row['driver_name'] not in history_dict: history_dict[row['driver_name']] = []
            history_dict[row['driver_name']].append((row['start_date'], row['group_name']))
        for k in history_dict: history_dict[k].sort(key=lambda x:x[0], reverse=True)
        
    _, last_day = calendar.monthrange(year, month)

    def get_day_html(day, is_horiz=True):
        d_str = f"{year}-{month:02d}-{day:02d}"
        wd_idx = datetime(year, month, day).weekday()
        
        today_sch = df_month[df_month['date'] == d_str] if not df_month.empty else pd.DataFrame()
        today_evt = df_events_month[df_events_month['date'] == d_str] if not df_events_month.empty else pd.DataFrame()
        
        full_stat, short_stat = get_stats_optimized(d_str, all_drivers, today_sch, history_dict)
        
        box_style = ""
        if d_str == now.strftime("%Y-%m-%d"):
            box_style = "box-shadow: inset 0 0 0 2px #fbc02d; background-color: #fff9c4;" 
        elif d_str == (now + timedelta(days=1)).strftime("%Y-%m-%d"):
            box_style = "box-shadow: inset 0 0 0 1px #ef5350; background-color: #ffebee;" 
        else:
            box_style = "background-color: white;"

        day_color = "#333"
        if wd_idx == 6 or is_holiday(datetime(year, month, day)): day_color = "#d32f2f"
        elif wd_idx == 5: day_color = "#1976D2"
        
        html = f'<div class="calendar-day-box {"calendar-day-box-horiz" if is_horiz else "calendar-day-box-grid"}" style="{box_style}">'
        html += f'<div class="day-header"><div style="display:flex; justify-content:space-between; padding:0 3px;"><span style="font-weight:bold; color:{day_color};">{day}일({WEEKDAY_KOREAN[wd_idx]})</span><span style="font-size:11px;">{len(today_sch)}명</span></div>'
        html += f'<div class="group-info-box">{get_daily_shift_summary(d_str)}</div></div>'
        if is_horiz: html += f'<div class="daily-stats-box" title="{full_stat}">{short_stat}</div>'
        
        html += '<div class="event-container">'
        if not today_evt.empty:
            for _, e in today_evt.iterrows(): html += f"<div style='background:#E3F2FD; color:#1565C0; font-size:10px; text-align:center;'>{e['title']}</div>"
        html += '</div>'
        
        if not is_horiz and not today_sch.empty:
            today_sch['rank'] = today_sch['type'].map(lambda x: SORT_ORDER.get(x, 99))
            today_sch = today_sch.sort_values(by=['rank', 'name'])
            for _, row in today_sch.iterrows():
                col = get_type_color(row['type'])
                n_txt = row['name']
                if row['note']: n_txt += f" {row['note']}"
                html += f"<div class='schedule-bar bar-single' style='background:{col}; border:1px solid #222; color:white;' title='{row['note']}'>{n_txt}</div>"
        html += '</div>'
        return html

    if "가로" in view_mode:
        l_map, m_row = calculate_layout_rows(df_month)
        h_html = '<div class="horizontal-scroll-container">'
        for d in range(1, last_day+1):
            d_str = f"{year}-{month:02d}-{d:02d}"
            h_html += get_day_html(d, True)[:-6]
            for r in range(m_row):
                if (d_str, r) in l_map:
                    it = l_map[(d_str, r)]
                    row = it['rec']
                    col = get_type_color(row['type'])
                    disp_text = row['name']
                    html += f"<div class='schedule-bar bar-single' style='background:{col}; border:1px solid #222; color:white;'>{disp_text}</div>"
                else: h_html += "<div class='schedule-spacer'></div>"
            h_html += "</div>"
        h_html += "</div>"
        st.markdown(h_html, unsafe_allow_html=True)
    else:
        cols = st.columns(7)
        for i, w in enumerate(WEEKDAY_KOREAN): cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:{'#d32f2f' if i==6 else '#1976D2' if i==5 else 'black'};'>{w}</div>", unsafe_allow_html=True)
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, d in enumerate(week):
                with cols[i]:
                    if d == 0: st.markdown("<div class='calendar-day-box' style='background:#f8f9fa;'></div>", unsafe_allow_html=True)
                    else: st.markdown(get_day_html(d, False), unsafe_allow_html=True)

def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황 (통합)")
    inject_custom_css()
    drivers = load_data("drivers")
    if drivers.empty: st.warning("승무원 없음"); return
    
    df_plan = load_data("schedules")
    if df_plan.empty or 'date' not in df_plan.columns: df_plan = pd.DataFrame(columns=['date', 'name', 'type', 'note'])
        
    df_work = load_data("work_history")
    required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub']
    if df_work.empty: df_work = pd.DataFrame(columns=required_cols)
    else:
        for c in required_cols:
            if c not in df_work.columns: df_work[c] = ""
    
    now = get_kst_now()
    if 'indiv_view_year' not in st.session_state: st.session_state.indiv_view_year = now.year
    if 'indiv_view_month' not in st.session_state: st.session_state.indiv_view_month = now.month
    if 'sb_ind_year' not in st.session_state: st.session_state.sb_ind_year = now.year
    if 'sb_ind_month' not in st.session_state: st.session_state.sb_ind_month = now.month
    
    c_nm, c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([2, 0.4, 0.8, 0.3, 0.7, 0.4, 0.4])
    
    with c_nm: target = st.selectbox("승무원 선택", drivers['name'].tolist(), key='sel_driver', label_visibility="collapsed")
    with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        st.selectbox("년도", range(2023, now.year + 3), key='sb_ind_year', label_visibility="collapsed")
        st.session_state.indiv_view_year = st.session_state.sb_ind_year

    with c_mo_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c_mo: 
        st.selectbox("월", range(1, 13), key='sb_ind_month', label_visibility="collapsed")
        st.session_state.indiv_view_month = st.session_state.sb_ind_month

    with c_prev: st.button("◀", key="i_prev_btn", on_click=prev_month_indiv)
    with c_next: st.button("▶", key="i_next_btn", on_click=next_month_indiv)
    
    st.divider()

    if target:
        year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
        filter_ym = f"{year}-{month:02d}"
        
        my_plan = df_plan[(df_plan['name']==target) & (df_plan['date'].astype(str).str.startswith(filter_ym))] if not df_plan.empty else pd.DataFrame()
        my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))] if not df_work.empty else pd.DataFrame()
        
        if not my_work.empty and 'shift' in my_work.columns:
            stats_am = len(my_work[my_work['shift'] == '오전'])
            stats_pm = len(my_work[my_work['shift'] == '오후'])
        else:
            stats_am, stats_pm = 0, 0
        
        y_filter = f"{year}-"
        y_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(y_filter))] if not df_work.empty else pd.DataFrame()
        if not y_work.empty and 'shift' in y_work.columns:
            y_am = len(y_work[y_work['shift'] == '오전'])
            y_pm = len(y_work[y_work['shift'] == '오후'])
        else:
            y_am, y_pm = 0, 0
        
        st.markdown(f"""
        <div style='display:flex; justify-content:center; gap:20px; margin-bottom:15px;'>
            <div style='background:#E3F2FD; padding:10px 20px; border-radius:10px; text-align:center; border:1px solid #90CAF9;'>
                <div style='font-size:12px; font-weight:bold; color:#1565C0;'>📅 {month}월 근무</div>
                <div style='font-size:14px;'>오전 <span style='color:blue; font-weight:bold;'>{stats_am}</span> / 오후 <span style='color:red; font-weight:bold;'>{stats_pm}</span></div>
            </div>
            <div style='background:#FFF3E0; padding:10px 20px; border-radius:10px; text-align:center; border:1px solid #FFCC80;'>
                <div style='font-size:12px; font-weight:bold; color:#E65100;'>📈 {year}년 누적</div>
                <div style='font-size:14px;'>오전 <span style='color:blue; font-weight:bold;'>{y_am}</span> / 오후 <span style='color:red; font-weight:bold;'>{y_pm}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        gh = load_data("group_history")
        h_dict = {}
        if not gh.empty:
            for _, r in gh.iterrows():
                if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
                h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
            for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
            
        cols = st.columns(7)
        for w in WEEKDAY_KOREAN: cols[WEEKDAY_KOREAN.index(w)].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
        
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, day in enumerate(week):
                with cols[i]:
                    if day == 0: st.write("")
                    else:
                        d_str = f"{year}-{month:02d}-{day:02d}"
                        grp = get_group_from_dict(h_dict, target, d_str)
                        auto = calculate_auto_shift(grp, d_str)
                        
                        cell_bg = "transparent"
                        txt = ""
                        
                        p_work = my_work[my_work['date'] == d_str] if not my_work.empty else pd.DataFrame()
                        p_plan = my_plan[my_plan['date'] == d_str] if not my_plan.empty else pd.DataFrame()
                        
                        if not p_work.empty:
                            w_row = p_work.iloc[0]
                            is_sub = (str(w_row['is_sub']).upper() == 'Y')
                            
                            txt_color = "white"
                            if w_row['shift'] == '오전': cell_bg = "#1e88e5" 
                            elif w_row['shift'] == '오후': cell_bg = "#e53935" 
                            if is_sub: cell_bg = "#8e24aa"
                            
                            txt = f"""<span style='color:white; font-weight:bold; font-size:11px;'>{w_row['route']} {w_row['seq']}번<br>({w_row['car']})</span><br>
                                      <span style='font-size:12px; color:white; font-weight:bold;'>{w_row['shift']}</span>"""
                            
                        elif not p_plan.empty:
                            pl_row = p_plan.iloc[0]
                            t = pl_row['type']
                            if t == "휴무": cell_bg = "#00592D"; txt = "<span style='color:white;'>휴무</span>"
                            else: cell_bg = get_type_color(t); txt = f"<span style='color:white;'>{t}</span>"
                        else:
                            if auto == "오전": cell_bg="#e3f2fd"; txt=f"<span style='color:blue;'>오전 ({grp})</span>"
                            elif auto == "오후": cell_bg="#fff3e0"; txt=f"<span style='color:red;'>오후 ({grp})</span>"
                            elif auto == "휴무": cell_bg="#f1f3f5"; txt=f"<span style='color:#999;'>휴무 ({grp})</span>"
                            
                        st.markdown(f"""
                        <div style='background-color:{cell_bg}; border:1px solid #ddd; border-radius:5px; min-height:80px; height:auto; padding:5px; display:flex; flex-direction:column; justify-content:center; align-items:center;'>
                            <div style='font-weight:bold; font-size:14px; color:#333; margin-bottom:2px;'>{day}</div>
                            <div style='text-align:center; font-size:12px; line-height:1.2;'>{txt}</div>
                        </div>""", unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="우진교통 배차 관리 시스템", layout="wide")
    inject_custom_css()
    
    now = get_kst_now()
    if 'view_year' not in st.session_state: st.session_state.view_year = now.year
    if 'view_month' not in st.session_state: st.session_state.view_month = now.month
    if 'indiv_view_year' not in st.session_state: st.session_state.indiv_view_year = now.year
    if 'indiv_view_month' not in st.session_state: st.session_state.indiv_view_month = now.month

    if 'auth_status' not in st.session_state: st.session_state['auth_status'] = None
    if st.session_state['auth_status'] is None:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.title("우진교통 배차 관리 시스템")
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            if st.button("로그인", type="primary", use_container_width=True):
                user = login_user(uid, upw)
                if user:
                    st.session_state['auth_status'] = user[0]
                    st.session_state['user_name'] = user[1]
                    log_login_access(uid, user[1])
                    st.rerun()
                else: st.error("로그인 실패")
            st.markdown('</div>', unsafe_allow_html=True)
        return
    
    c_head1, c_head2 = st.columns([8, 1])
    with c_head1: st.title(f"우진교통 배차 관리 시스템 ({st.session_state.get('user_name')}님)")
    with c_head2: 
        if st.button("로그아웃"): st.session_state['auth_status']=None; st.rerun()
    
    if st.session_state['auth_status'] == 'admin':
        t1, t2, t3, t4, t5, t6 = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력/배차", "⚙️ 승무원", "📊 조회", "🔧 로그"])
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
