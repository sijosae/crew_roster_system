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

# [수정] 콜백 함수: 세션 상태를 직접 제어하여 버튼 클릭 시 즉시 반영
def prev_cal_callback():
    if st.session_state.view_month == 1:
        st.session_state.view_year -= 1
        st.session_state.view_month = 12
    else:
        st.session_state.view_month -= 1

def next_cal_callback():
    if st.session_state.view_month == 12:
        st.session_state.view_year += 1
        st.session_state.view_month = 1
    else:
        st.session_state.view_month += 1

def prev_month_indiv():
    if st.session_state.indiv_view_month == 1:
        st.session_state.indiv_view_year -= 1
        st.session_state.indiv_view_month = 12
    else:
        st.session_state.indiv_view_month -= 1

def next_month_indiv():
    if st.session_state.indiv_view_month == 12:
        st.session_state.indiv_view_year += 1
        st.session_state.indiv_view_month = 1
    else:
        st.session_state.indiv_view_month += 1

if 'system_logs' not in st.session_state: st.session_state['system_logs'] = []
if 'action_logs' not in st.session_state: st.session_state['action_logs'] = []
if 'last_error_msg' not in st.session_state: st.session_state['last_error_msg'] = None

# [초기화] 날짜가 없으면 오늘 날짜로 세팅
now_init = get_kst_now()
if 'view_year' not in st.session_state: st.session_state.view_year = now_init.year
if 'view_month' not in st.session_state: st.session_state.view_month = now_init.month
if 'indiv_view_year' not in st.session_state: st.session_state.indiv_view_year = now_init.year
if 'indiv_view_month' not in st.session_state: st.session_state.indiv_view_month = now_init.month

def add_log(msg, ids=None, sheet_name=None, level="INFO"):
    timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"time": timestamp, "msg": msg, "level": level, "ids": ids if ids else [], "sheet": sheet_name, "status": "active"}
    st.session_state['action_logs'].insert(0, log_entry)

def log_login_access(username, name):
    try:
        sh = get_db_connection()
        try: ws = sh.worksheet("access_logs")
        except: 
            ws = sh.add_worksheet(title="access_logs", rows=1000, cols=4)
            ws.append_row(["timestamp", "username", "name", "status"])
        ws.append_row([get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), username, name, "Login Success"])
        st.cache_data.clear()
    except: pass

# ==========================================
# 1. DB 연결 (영구 캐싱)
# ==========================================
@st.cache_resource
def get_cached_sheet_object():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_json" in st.secrets: creds_dict = json.loads(st.secrets["gcp_json"])
        else:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("bus_schedule_db")
    except Exception as e: return None

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
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=['date']) 
        return df
    except: return pd.DataFrame()

def clear_cache_after_save(): st.cache_data.clear()

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
        try: rows_to_delete.append(col_values.index(target_id) + 1)
        except: continue
    for r_idx in sorted(rows_to_delete, reverse=True): ws.delete_rows(r_idx)
    clear_cache_after_save()
    return True

def make_hash(password): return hashlib.sha256(str(password).encode()).hexdigest()

def login_user(username, password):
    df = load_data("users")
    if df.empty: return None
    pw_hash = make_hash(password)
    if 'username' not in df.columns: return None
    user = df[(df['username'].astype(str) == username) & (df['password'] == pw_hash)]
    return (user.iloc[0]['role'], user.iloc[0]['name']) if not user.empty else None

def add_user_account(username, password, role, name):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    ws.append_row([username, make_hash(password), role, name, get_kst_now().strftime("%Y-%m-%d")])
    clear_cache_after_save()
    return True

def delete_user_account(username):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        cell = ws.find(username)
        if cell: ws.delete_rows(cell.row); clear_cache_after_save()
    except: pass

def update_user_password(username, new_password):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        cell = ws.find(username)
        if cell: ws.update_cell(cell.row, 2, make_hash(new_password)); clear_cache_after_save(); return True
    except: pass
    return False

# ==========================================
# 3. 데이터 저장 로직
# ==========================================
def add_driver_with_group(name, group_name, start_date="2020-01-01"):
    sh = get_db_connection()
    ws_drivers = sh.worksheet("drivers")
    try:
        if not ws_drivers.find(name): ws_drivers.append_row(["", name, group_name, get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), ""])
    except: pass
    sh.worksheet("group_history").append_row(["", name, group_name, start_date, get_kst_now().strftime("%Y-%m-%d %H:%M:%S")])
    clear_cache_after_save()
    return True

def set_driver_resignation(name, r_date):
    sh = get_db_connection()
    ws = sh.worksheet("drivers")
    try:
        cell = ws.find(name)
        if cell: ws.update_cell(cell.row, 5, r_date); clear_cache_after_save()
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
    base_id = get_kst_now().strftime("%y%m%d%H%M") 
    rows = []
    cnt = 0
    for name in name_list:
        for d in dates:
            rows.append([f"{base_id}{cnt:02d}", name, d.strftime("%Y-%m-%d"), type, note, get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), shift])
            cnt+=1
    if rows:
        sh = get_db_connection()
        sh.worksheet("schedules").append_rows(rows)
        clear_cache_after_save()
    return len(rows), [r[0] for r in rows]

def add_company_event(date, title):
    sh = get_db_connection()
    sh.worksheet("company_events").append_row([get_kst_now().strftime("%y%m%d%H%M%S"), date, title, get_kst_now().strftime("%Y-%m-%d")])
    clear_cache_after_save()
    return 

# ==========================================
# 4. 분석 엔진 (감차/엑셀)
# ==========================================
kr_holidays = holidays.KR()
def is_holiday_or_weekend(date_obj): return date_obj.weekday() >= 5 or date_obj in kr_holidays

def clean_driver_name(name):
    if pd.isna(name): return "" 
    s = str(name).strip()
    if s.lower() == "nan" or s == "": return ""
    s = re.sub(r'\(.*?\)', '', s) 
    return s.replace(" ", "").strip()

def get_reduction_rules():
    df = load_data("reduction_rules")
    rules = []
    if not df.empty and 'start_date' in df.columns:
        for _, row in df.iterrows():
            rules.append({
                'start': row['start_date'], 'end': row['end_date'],
                'route': str(row['route']).strip(), 'seq': str(row['sequence']).strip(),
                'condition': row['condition']
            })
    return rules

def is_reduction_target(date_str, route, seq, rules):
    try: d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except: return False
    is_holi = is_holiday_or_weekend(d)
    r_target = str(route).strip()
    s_target = str(seq).strip()
    for r in rules:
        if r['start'] <= date_str <= r['end']:
            if r['route'] == r_target and r['seq'] == s_target:
                if r['condition'] == 'Always': return True
                if r['condition'] == 'Weekend/Holiday' and is_holi: return True
    return False

def parse_roster_excel(file):
    df_raw = pd.read_excel(file, header=None)
    date_rows = []
    for idx, row in df_raw.iterrows():
        if "202" in str(row[0]) or "년" in str(row[0]):
            try:
                if pd.notnull(df_raw.iloc[idx, 3]) and pd.notnull(df_raw.iloc[idx, 5]): date_rows.append(idx)
            except: pass
    extracted_data = [] 
    for start_row in date_rows:
        try:
            y = int(str(df_raw.iloc[start_row, 0]).replace("년","").strip())
            m = int(str(df_raw.iloc[start_row, 3]).replace("월","").strip())
            d = int(str(df_raw.iloc[start_row, 5]).replace("일","").strip())
            curr_date = datetime(y, m, d).strftime("%Y-%m-%d")
        except: continue 
        cols = [{'route':1, 'seq':2, 'car':3, 'am':4, 'am_sub':5, 'pm':6, 'pm_sub':7}, 
                {'route':9, 'seq':10, 'car':11, 'am':12, 'am_sub':13, 'pm':14, 'pm_sub':15}]
        for side in cols:
            last_route = None
            for r_off in range(3, 75): 
                c_idx = start_row + r_off
                if c_idx >= len(df_raw): break
                raw_route = df_raw.iloc[c_idx, side['route']]
                if pd.notnull(raw_route) and str(raw_route).strip(): last_route = str(raw_route).strip()
                curr_route = last_route if last_route else ""
                curr_seq = str(df_raw.iloc[c_idx, side['seq']]).strip() if pd.notnull(df_raw.iloc[c_idx, side['seq']]) else ""
                raw_car = df_raw.iloc[c_idx, side['car']]
                try: 
                    car_num = int(re.sub(r'[^0-9]', '', str(raw_car).strip()))
                    valid_car = (5001 <= car_num <= 5300)
                    curr_car = str(car_num)
                except: valid_car, curr_car = False, ""
                if not (curr_route and curr_seq and valid_car): continue
                am = clean_driver_name(df_raw.iloc[c_idx, side['am']])
                am_s = clean_driver_name(df_raw.iloc[c_idx, side['am_sub']])
                am_f = am_s if am_s else am
                pm = clean_driver_name(df_raw.iloc[c_idx, side['pm']])
                pm_s = clean_driver_name(df_raw.iloc[c_idx, side['pm_sub']])
                pm_f = pm_s if pm_s else pm
                if am_f: extracted_data.append({'date':curr_date, 'name':am_f, 'shift':'오전', 'route':curr_route, 'seq':curr_seq, 'car':curr_car, 'is_sub':bool(am_s), 'orig_fix':am})
                if pm_f: extracted_data.append({'date':curr_date, 'name':pm_f, 'shift':'오후', 'route':curr_route, 'seq':curr_seq, 'car':curr_car, 'is_sub':bool(pm_s), 'orig_fix':pm})
    return pd.DataFrame(extracted_data)

def save_work_history(df_new):
    sh = get_db_connection()
    try: ws = sh.worksheet("work_history")
    except: ws = sh.add_worksheet("work_history", 1000, 10); ws.append_row(['date','name','shift','route','seq','car','is_sub','orig_fix','updated_at'])
    exist = ws.get_all_values()
    df_old = pd.DataFrame(exist[1:], columns=exist[0]) if len(exist) > 1 else pd.DataFrame()
    cols = ['date','name','shift','route','seq','car','is_sub','orig_fix','updated_at']
    for c in cols:
        if c not in df_new.columns: df_new[c] = ""
        if not df_old.empty and c not in df_old.columns: df_old[c] = ""
    df_final = pd.concat([df_old[cols], df_new[cols]]).drop_duplicates(subset=['date','name','shift'], keep='last').sort_values(['date','name'])
    ws.clear(); ws.append_row(cols); ws.append_rows(df_final.fillna("").astype(str).values.tolist())
    clear_cache_after_save(); return len(df_new)

def add_reduction_rule(start, end, route, seq, cond):
    sh = get_db_connection()
    try: ws = sh.worksheet("reduction_rules")
    except: ws = sh.add_worksheet("reduction_rules", 100, 5); ws.append_row(['start_date','end_date','route','sequence','condition'])
    ws.append_row([str(start), str(end), str(route), str(seq), cond]); clear_cache_after_save()

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
        off = offs.get(group_name); return None if off is None else pat[((tgt - ref).days + off) % 10]
    except: return None

def get_group_from_dict(history_dict, name, target_date_str):
    if name not in history_dict: return None
    for start_date, group in history_dict[name]:
        if start_date <= target_date_str: return group
    return None

def get_type_color(type_name):
    colors = { "휴무": "#00592D", "교육": "#8c6b4a", "경조사": "#1F3994", "징계": "#000000", "당일 해지": "#8B0000", "병가": "#A52A2A", "휴직": "#D2691E", "기타": "#363636" }
    return colors.get(type_name, "#546E7A")

def get_daily_shift_summary(date_str):
    am, pm, off_am, off_pm = [], [], [], []
    prev_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    for i in range(1, 11):
        grp = f"{i}조"
        s = calculate_auto_shift(grp, date_str)
        if s == "오전": am.append(str(i))
        elif s == "오후": pm.append(str(i))
        else:
            if calculate_auto_shift(grp, prev_date) == "오전": off_am.append(str(i))
            else: off_pm.append(str(i))
    return f"<div style='display:flex; justify-content:space-between; font-size:10px;'><span style='color:#1c7ed6'>전:{','.join(am)}</span><span style='color:#868e96'>휴:{','.join(off_am)}</span></div><div style='display:flex; justify-content:space-between; font-size:10px;'><span style='color:#d9480f'>후:{','.join(pm)}</span><span style='color:#868e96'>휴:{','.join(off_pm)}</span></div>"

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
                c_end = row['date']; c_recs.append(row)
            else:
                segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
                c_name, c_type, c_start, c_end = row['name'], row['type'], row['date'], row['date']
                c_recs = [row]
        segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
    lanes = {}
    layout_map = {}
    for seg in segments:
        seg_dates = [rec['date'] for rec in seg['records']]
        r = 0
        while True:
            if r not in lanes: lanes[r] = set(); break
            if not lanes[r].intersection(seg_dates): break
            r += 1
        lanes[r].update(seg_dates)
        for idx, rec in enumerate(seg['records']):
            layout_map[(rec['date'], r)] = {'rec': rec, 'is_start': idx==0, 'is_end': idx==len(seg['records'])-1, 'duration': len(seg['records'])}
    return layout_map, (max(lanes.keys()) + 1 if lanes else 0)

def get_stats_optimized(date_str, all_drivers_df, today_schedules_df, history_dict):
    active = len([d for _, d in all_drivers_df.iterrows() if not d.get('resigned_date') or d['resigned_date'] >= date_str])
    return f"총 {active}명", ""

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
    prefix, suffix, period_text = "", "", f"(~{end_date.month}/{end_date.day})"
    if duration >= 2:
        if p_date_str == start_date.strftime("%Y-%m-%d"): prefix = "➡️"
        if p_date_str == end_date.strftime("%Y-%m-%d"): suffix = "🛑"
    return prefix, suffix, period_text

def inject_custom_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; }
        div[data-testid="column"] { padding: 0px !important; gap: 0px !important; }
        .horizontal-scroll-container { display: flex; overflow-x: auto; gap: 0px; padding-bottom: 15px; width: 100%; }
        .calendar-day-box { border: 1px solid #e9ecef; min-height: 120px; padding: 0; background-color: white; display: flex; flex-direction: column; height: auto !important; }
        .calendar-day-box-horiz { flex: 0 0 90px; } 
        .calendar-day-box-grid { width: 100%; margin: 2px; }
        .horizontal-scroll-container::-webkit-scrollbar { height: 8px; }
        .horizontal-scroll-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        .horizontal-scroll-container::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
        .daily-stats-box { background-color: #f1f3f5; border-bottom: 1px solid #e9ecef; font-size: 11px; text-align: center; padding: 3px 0; color: #495057; font-weight: bold; }
        .group-info-box { font-size: 10px; padding: 2px 4px; background-color: transparent; border-bottom: 1px solid #f1f3f5; line-height: 1.2; font-weight: bold; }
        .event-container { height: 46px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; border-bottom: 1px solid #f1f3f5; padding: 2px 1px; }
        .event-container::-webkit-scrollbar { display: none; }
        .day-header { display: flex; flex-direction: column; padding-top: 4px; padding-bottom: 4px; gap: 1px; justify-content: center; background-color: transparent; border-bottom: 1px solid #eee; }
        .schedule-bar { color: white; padding: 0 2px; margin-bottom: 1px; line-height: 1.1; text-align: center; cursor: help; font-size: 11px; height: 34px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; border-top: none; border-bottom: none; }
        .bar-start { border-top-left-radius: 4px; border-bottom-left-radius: 4px; margin-right: -10px !important; margin-left: 2px; z-index: 2; }
        .bar-mid { border-radius: 0; margin-left: -10px !important; margin-right: -10px !important; z-index: 1; }
        .bar-end { border-top-right-radius: 4px; border-bottom-right-radius: 4px; margin-left: -10px !important; margin-right: 2px; z-index: 2; }
        .bar-single { border-radius: 4px; margin: 0 2px 1px 2px; z-index: 3; }
        .schedule-spacer { height: 34px; margin-bottom: 1px; background-color: transparent; }
        button[kind="primary"], div[data-testid="stButton"] button { background-color: #00592D !important; border-color: #00592D !important; color: white !important; }
        button[kind="primary"]:hover, div[data-testid="stButton"] button:hover { background-color: #004d26 !important; border-color: #004d26 !important; color: white !important; }
        @media (max-width: 640px) { h1 { font-size: 1.6rem !important; } }
    </style>
    """, unsafe_allow_html=True)

def render_calendar_tab():
    c_title, c_legend, c_view = st.columns([1, 1.5, 0.8])
    with c_title: st.markdown("### 📅 월간 휴무 신청 현황")
    with c_legend:
        st.markdown("".join([f"<span style='background:{get_type_color(t)}; color:white; padding:2px 6px; margin-right:4px; border-radius:4px; font-size:10px;'>{t}</span>" for t in ["휴무","교육","경조사","병가","연차"]]), unsafe_allow_html=True)
    with c_view: view_mode = st.radio("보기", ["가로 스크롤", "달력"], horizontal=True, label_visibility="collapsed")
    inject_custom_css()
    now = get_kst_now()
    
    # [수정] 달력 컨트롤 한줄 배치
    c1, c2, c3, c4, c5, c6, c7 = st.columns([0.3, 0.7, 0.3, 0.7, 0.4, 0.4, 1.2])
    with c1: st.markdown("<div style='padding-top:10px; text-align:right; font-weight:bold;'>년도:</div>", unsafe_allow_html=True)
    with c2: 
        years = list(range(2023, now.year + 3))
        try: idx = years.index(st.session_state.view_year)
        except: idx = 1
        st.selectbox("년도", years, index=idx, key='sb_view_year', label_visibility="collapsed")
        if st.session_state.sb_view_year != st.session_state.view_year:
            st.session_state.view_year = st.session_state.sb_view_year; st.rerun()

    with c3: st.markdown("<div style='padding-top:10px; text-align:right; font-weight:bold;'>월:</div>", unsafe_allow_html=True)
    with c4: 
        st.selectbox("월", range(1, 13), index=st.session_state.view_month-1, key='sb_view_month', label_visibility="collapsed")
        if st.session_state.sb_view_month != st.session_state.view_month:
            st.session_state.view_month = st.session_state.sb_view_month; st.rerun()

    with c5: st.button("◀", key="prev_cal_btn", on_click=prev_cal_callback)
    with c6: st.button("▶", key="next_cal_btn", on_click=next_cal_callback)
    with c7:
        if st.session_state.get('auth_status') == 'admin':
            if st.button("➕ 빠른 입력", type="primary"): show_input_dialog()
    st.divider()
    
    df = load_data("schedules")
    year, month = st.session_state.view_year, st.session_state.view_month
    df_month = df[df['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df.empty else pd.DataFrame()
    full_schedule_map = {}
    if not df.empty:
        for _, row in df.iterrows(): full_schedule_map[(row['name'], str(row['date']))] = row['type']
    
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
        
        # [수정] 하이라이트 박스 전체 적용 (box-shadow)
        box_style = ""
        if d_str == now.strftime("%Y-%m-%d"): box_style = "box-shadow: inset 0 0 0 2px #fbc02d; background-color: #fff9c4;"
        elif d_str == (now + timedelta(days=1)).strftime("%Y-%m-%d"): box_style = "box-shadow: inset 0 0 0 1px #ef5350; background-color: #ffebee;"
        
        day_color = "#333"
        if wd_idx == 6 or is_holiday(datetime(year, month, day)): day_color = "#d32f2f"
        elif wd_idx == 5: day_color = "#1976D2"
        
        html = f'<div class="calendar-day-box {"calendar-day-box-horiz" if is_horiz else "calendar-day-box-grid"}" style="{box_style}">'
        html += f'<div class="day-header"><div style="display:flex; justify-content:space-between; padding:0 3px;"><span style="font-weight:bold; color:{day_color};">{day}일({WEEKDAY_KOREAN[wd_idx]})</span><span style="font-size:11px;">{len(today_sch)}명</span></div>'
        html += f'<div class="group-info-box">{get_daily_shift_summary(d_str)}</div></div>'
        if is_horiz: html += f'<div class="daily-stats-box">총 {len(today_sch)}명</div>'
        
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
                    cls = "bar-single"
                    if it['duration'] > 1:
                        if it['is_start']: cls = "bar-start"
                        elif it['is_end']: cls = "bar-end"
                        else: cls = "bar-mid"
                    h_html += f"<div class='schedule-bar {cls}' style='background:{col};' title='{row['name']}'>{row['name']}</div>"
                else:
                    h_html += "<div class='schedule-spacer'></div>"
            h_html += "</div>"
        h_html += "</div>"
        st.markdown(h_html, unsafe_allow_html=True)
    else:
        cols = st.columns(7)
        for w in WEEKDAY_KOREAN: cols[WEEKDAY_KOREAN.index(w)].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, d in enumerate(week):
                with cols[i]:
                    if d == 0: st.markdown("<div style='height:100px; background:#f8f9fa;'></div>", unsafe_allow_html=True)
                    else: st.markdown(get_day_html(d, False), unsafe_allow_html=True)

def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황 (통합)")
    inject_custom_css()
    drivers = load_data("drivers")
    if drivers.empty: st.warning("승무원 없음"); return

    df_work = load_data("work_history")
    if df_work.empty: df_work = pd.DataFrame(columns=['date','name','shift','route','seq','car','is_sub'])
    for c in ['date','name','shift','route','seq','car','is_sub']: 
        if c not in df_work.columns: df_work[c] = ""
    
    red_rules = get_reduction_rules()
    now = get_kst_now()
    
    # [수정] 인터페이스 한줄 & 버튼 동기화
    c_nm, c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([2, 0.4, 0.8, 0.3, 0.7, 0.4, 0.4])
    with c_nm: target = st.selectbox("승무원 선택", drivers['name'].tolist(), key='sel_driver', label_visibility="collapsed")
    with c_yr_txt: st.markdown("<div style='padding-top:10px; text-align:right; font-weight:bold;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        years = list(range(2023, now.year + 3))
        try: idx = years.index(st.session_state.indiv_view_year)
        except: idx = 1
        st.selectbox("년도", years, index=idx, key='sb_ind_year', label_visibility="collapsed")
        if st.session_state.sb_ind_year != st.session_state.indiv_view_year:
            st.session_state.indiv_view_year = st.session_state.sb_ind_year; st.rerun()

    with c_mo_txt: st.markdown("<div style='padding-top:10px; text-align:right; font-weight:bold;'>월:</div>", unsafe_allow_html=True)
    with c_mo: 
        st.selectbox("월", range(1, 13), index=st.session_state.indiv_view_month-1, key='sb_ind_month', label_visibility="collapsed")
        if st.session_state.sb_ind_month != st.session_state.indiv_view_month:
            st.session_state.indiv_view_month = st.session_state.sb_ind_month; st.rerun()

    with c_prev: st.button("◀", key="i_prev", on_click=prev_month_indiv)
    with c_next: st.button("▶", key="i_next", on_click=next_month_indiv)
    
    st.divider()

    if target:
        year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
        filter_ym = f"{year}-{month:02d}"
        
        my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))]
        month_data_exists = not df_work[df_work['date'].astype(str).str.startswith(filter_ym)].empty
        
        cnt_am = len(my_work[my_work['shift']=='오전'])
        cnt_pm = len(my_work[my_work['shift']=='오후'])
        st.markdown(f"<div style='text-align:center; margin-bottom:10px; font-weight:bold;'>{year}년 {month}월: 오전 {cnt_am} / 오후 {cnt_pm}</div>", unsafe_allow_html=True)
        
        cols = st.columns(7)
        for w in WEEKDAY_KOREAN: cols[WEEKDAY_KOREAN.index(w)].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
        
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, day in enumerate(week):
                with cols[i]:
                    if day == 0: st.write("")
                    else:
                        d_str = f"{year}-{month:02d}-{day:02d}"
                        w_row = my_work[my_work['date'] == d_str]
                        
                        bg = "white"
                        txt = ""
                        
                        if not w_row.empty:
                            r = w_row.iloc[0]
                            bg = "#E3F2FD" if r['shift']=='오전' else "#FFEBEE"
                            txt_c = "blue" if r['shift']=='오전' else "red"
                            
                            # [수정] 박스 글자 잘림 방지 (white-space: normal)
                            txt = f"<span style='font-size:12px; color:{txt_c}; font-weight:bold; white-space: normal;'>{r['route']} {r['seq']} ({r['car']})<br>{r['shift']}</span>"
                        elif month_data_exists:
                            bg = "#E8F5E9"
                            txt = "<span style='color:green; font-weight:bold;'>휴무</span>"
                            # [추가] 감차 휴무 표시
                            if is_reduction_target(d_str, "", "", red_rules): # 고정차 정보가 없어서 정확한 감차 판별 불가하지만 날짜기준으로라도 체크
                                txt = "<span style='color:green; font-weight:bold;'>⛔ 감차 휴무</span>"
                        else:
                            txt = "-"

                        # [수정] 하이라이트 박스 전체 적용
                        box_style = ""
                        if d_str == now.strftime("%Y-%m-%d"): box_style = "box-shadow: inset 0 0 0 2px #fbc02d;"
                        elif d_str == (now + timedelta(days=1)).strftime("%Y-%m-%d"): box_style = "box-shadow: inset 0 0 0 1px #ef5350;"
                        
                        st.markdown(f"""
                        <div style='background-color:{bg}; {box_style} border:1px solid #ddd; border-radius:5px; min-height:80px; height:auto; padding:5px; display:flex; flex-direction:column; align-items:center; justify-content:center;'>
                            <div style='font-weight:bold; font-size:14px; margin-bottom:3px; color:{'black'};'>{day}</div>
                            <div style='text-align:center; word-break: break-word;'>{txt}</div>
                        </div>""", unsafe_allow_html=True)

def render_view_manage_tab():
    st.subheader("📊 데이터 조회")
    df = load_data("schedules")
    if not df.empty: st.dataframe(df)

def render_public_search_tab(): render_view_manage_tab()

def main():
    st.set_page_config(page_title="우진교통 배차 관리 시스템", layout="wide")
    inject_custom_css()
    
    if 'auth_status' not in st.session_state: st.session_state['auth_status'] = None

    if st.session_state['auth_status'] is None:
        c1, c2, c3 = st.columns([1,1,1])
        with c2:
            st.title("우진교통 배차 관리")
            id_Input = st.text_input("아이디")
            pw_Input = st.text_input("비밀번호", type="password")
            if st.button("로그인", type="primary", use_container_width=True):
                user = login_user(id_Input, pw_Input)
                if user:
                    st.session_state['auth_status'] = user[0]
                    st.session_state['user_name'] = user[1]
                    log_login_access(id_Input, user[1])
                    st.rerun()
                else: st.error("로그인 실패")
        return

    c_h1, c_h2 = st.columns([8, 1])
    with c_h1: st.title(f"우진교통 배차 관리 ({st.session_state['user_name']})")
    with c_h2: 
        if st.button("로그아웃"): st.session_state['auth_status']=None; st.rerun()

    if st.session_state['auth_status'] == 'admin':
        t1, t2, t3, t4, t5, t6 = st.tabs(["📅 월간현황", "👤 개인별", "📝 입력", "⚙️ 승무원", "📊 조회", "🔧 로그"])
        with t1: render_calendar_tab()
        with t2: render_individual_calendar_tab()
        with t3: render_input_tab()
        with t4: render_driver_manage_tab()
        with t5: render_view_manage_tab()
        with t6: render_log_tab()
    else:
        t1, t2 = st.tabs(["📅 월간현황", "👤 개인별"])
        with t1: render_calendar_tab()
        with t2: render_individual_calendar_tab()

if __name__ == '__main__':
    main()
