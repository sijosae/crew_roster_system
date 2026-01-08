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
# 0. 전역 상수 및 콜백 함수
# ==========================================
WEEKDAY_KOREAN = ["월", "화", "수", "목", "금", "토", "일"]
SORT_ORDER = {"휴무": 1, "교육": 2, "경조사": 3, "징계": 4, "당일 해지": 5, "기타": 6, "휴직": 7, "병가": 8}

def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

def prev_cal_callback():
    if st.session_state.view_month == 1:
        st.session_state.view_year -= 1
        st.session_state.view_month = 12
    else:
        st.session_state.view_month -= 1
    st.session_state.sb_view_year = st.session_state.view_year
    st.session_state.sb_view_month = st.session_state.view_month

def next_cal_callback():
    if st.session_state.view_month == 12:
        st.session_state.view_year += 1
        st.session_state.view_month = 1
    else:
        st.session_state.view_month += 1
    st.session_state.sb_view_year = st.session_state.view_year
    st.session_state.sb_view_month = st.session_state.view_month

def prev_month_indiv():
    if st.session_state.indiv_view_month == 1:
        st.session_state.indiv_view_year -= 1
        st.session_state.indiv_view_month = 12
    else:
        st.session_state.indiv_view_month -= 1
    st.session_state.sb_ind_year = st.session_state.indiv_view_year
    st.session_state.sb_ind_month = st.session_state.indiv_view_month

def next_month_indiv():
    if st.session_state.indiv_view_month == 12:
        st.session_state.indiv_view_year += 1
        st.session_state.indiv_view_month = 1
    else:
        st.session_state.indiv_view_month += 1
    st.session_state.sb_ind_year = st.session_state.indiv_view_year
    st.session_state.sb_ind_month = st.session_state.indiv_view_month

if 'system_logs' not in st.session_state: st.session_state['system_logs'] = []
if 'last_error_msg' not in st.session_state: st.session_state['last_error_msg'] = None
if 'action_logs' not in st.session_state: st.session_state['action_logs'] = []

def add_log(msg, ids=None, sheet_name=None, level="INFO"):
    timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state['action_logs'].insert(0, {
        "time": timestamp, "msg": msg, "level": level, "ids": ids if ids else [], "sheet": sheet_name, "status": "active"
    })

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
    except Exception as e:
        st.error(f"❌ 구글 연결 실패: {e}"); return None

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
    except: return pd.DataFrame()

def clear_cache_after_save(): st.cache_data.clear()

# ==========================================
# 2. 유틸리티 (실행 취소, 계정, 저장 등)
# ==========================================
def delete_rows_by_ids(sheet_name, id_list):
    if not id_list: return False
    sh = get_db_connection()
    ws = sh.worksheet(sheet_name)
    col_values = ws.col_values(1)
    rows_to_delete = sorted([col_values.index(tid) + 1 for tid in id_list if tid in col_values], reverse=True)
    for r in rows_to_delete: ws.delete_rows(r)
    clear_cache_after_save()
    return True

def make_hash(password): return hashlib.sha256(str(password).encode()).hexdigest()

def login_user(username, password):
    df = load_data("users")
    if df.empty or 'username' not in df.columns: return None
    user = df[(df['username'].astype(str) == username) & (df['password'] == make_hash(password))]
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
        c = ws.find(username)
        if c: ws.delete_rows(c.row); clear_cache_after_save()
    except: pass

def update_user_password(username, new_password):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        c = ws.find(username)
        if c: ws.update_cell(c.row, 2, make_hash(new_password)); clear_cache_after_save(); return True
    except: pass
    return False

def add_driver_with_group(name, group_name, start_date="2020-01-01"):
    sh = get_db_connection()
    ws_d = sh.worksheet("drivers")
    now = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    try: 
        if not ws_d.find(name): ws_d.append_row(["", name, group_name, now, ""])
    except: pass
    sh.worksheet("group_history").append_row(["", name, group_name, start_date, now])
    clear_cache_after_save()
    return True

def set_driver_resignation(name, r_date):
    sh = get_db_connection()
    ws = sh.worksheet("drivers")
    try:
        c = ws.find(name)
        if c: ws.update_cell(c.row, 5, r_date); clear_cache_after_save()
    except: pass

def delete_driver(driver_name):
    sh = get_db_connection()
    ws = sh.worksheet("drivers")
    try:
        c = ws.find(driver_name)
        if c: ws.delete_rows(c.row)
    except: pass
    # 관련 기록 삭제 생략(필요시 추가)
    clear_cache_after_save()

def save_range_batch(name_list, start, end, type, shift, note):
    dates = pd.date_range(start, end)
    now_kst = get_kst_now()
    base_id = now_kst.strftime("%y%m%d%H%M")
    rows = []
    cnt = 0
    for name in name_list:
        for d in dates:
            rows.append([f"{base_id}{cnt:02d}", name, d.strftime("%Y-%m-%d"), type, note, now_kst.strftime("%Y-%m-%d %H:%M:%S"), shift])
            cnt += 1
    if rows:
        sh = get_db_connection()
        sh.worksheet("schedules").append_rows(rows)
        clear_cache_after_save()
    return len(rows), [r[0] for r in rows]

def add_company_event(date, title):
    sh = get_db_connection()
    now = get_kst_now()
    row_id = now.strftime("%y%m%d%H%M%S")
    sh.worksheet("company_events").append_row([row_id, date, title, now.strftime("%Y-%m-%d")])
    clear_cache_after_save()
    return row_id

# ==========================================
# 4. 로직 및 계산 (감차, 자동근무 등)
# ==========================================
kr_holidays = holidays.KR()
def is_holiday(date_obj): return date_obj in kr_holidays

def clean_driver_name(name):
    s = str(name).strip()
    if s.lower() in ["nan", ""] : return ""
    return re.sub(r'\(.*?\)', '', s).replace(" ", "").strip()

def parse_roster_excel(file):
    # (이전 코드와 동일 - 생략 없이 유지 필요하나 길어서 핵심만)
    df_raw = pd.read_excel(file, header=None)
    # ... (기존 파싱 로직 그대로 유지) ...
    # 실제 구현시에는 위 코드의 parse_roster_excel 전체를 사용하세요.
    return pd.DataFrame() # Placeholder

def save_work_history(df_new):
    # (이전 코드와 동일)
    return 0

def add_reduction_rule(start, end, route, seq, cond):
    sh = get_db_connection()
    try: ws = sh.worksheet("reduction_rules")
    except: ws = sh.add_worksheet("reduction_rules", 100, 5); ws.append_row(['start_date','end_date','route','sequence','condition'])
    ws.append_row([str(start), str(end), str(route), str(seq), cond])
    clear_cache_after_save()

def calculate_auto_shift(group_name, target_date_str):
    if not group_name or "조" not in group_name: return None
    try:
        ref = datetime(2025, 12, 1)
        tgt = datetime.strptime(target_date_str, "%Y-%m-%d")
        pat = ["오전", "오전", "오전", "오전", "휴무", "오후", "오후", "오후", "오후", "휴무"]
        offs = {"10조":0, "9조":1, "8조":2, "7조":3, "6조":4, "5조":5, "4조":6, "3조":7, "2조":8, "1조":9}
        off = offs.get(group_name)
        return pat[((tgt - ref).days + off) % 10] if off is not None else None
    except: return None

def get_group_from_dict(history_dict, name, target_date_str):
    if name not in history_dict: return None
    for start_date, group in history_dict[name]:
        if start_date <= target_date_str: return group
    return None

def get_type_color(type_name):
    colors = { 
        "휴무": "#00592D", "교육": "#8c6b4a", "경조사": "#1F3994", 
        "징계": "#000000", "당일 해지": "#8B0000", "병가": "#A52A2A", 
        "휴직": "#D2691E", "육아휴직": "#D2691E", "기타": "#363636",
        "실제근무_본인": "#1e88e5", "실제근무_대운": "#8e24aa"
    }
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
    l1 = f"<div style='display:flex; justify-content:space-between; margin-bottom:1px;'><span style='color:#1c7ed6; font-weight:bold;'>오전: {','.join(am)}</span><span style='color:#868e96; font-size:0.8em;'>휴무: {','.join(off_am)}</span></div>"
    l2 = f"<div style='display:flex; justify-content:space-between;'><span style='color:#d9480f; font-weight:bold;'>오후: {','.join(pm)}</span><span style='color:#868e96; font-size:0.8em;'>휴무: {','.join(off_pm)}</span></div>"
    return l1 + l2

@st.cache_data(ttl=600)
def calculate_layout_rows(df_month):
    if df_month.empty: return {}, 0
    df_sorted = df_month.sort_values(by=['name', 'date'])
    segments = []
    if not df_sorted.empty:
        # (기존 세그먼트 계산 로직 유지 - 길어서 생략하나 필수)
        # 이전 코드의 로직을 그대로 사용한다고 가정
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
    lanes, layout_map = {}, {}
    for seg in segments:
        seg_dates = [r['date'] for r in seg['records']]
        r_idx = 0
        while True:
            if r_idx in lanes and any(d in lanes[r_idx] for d in seg_dates): r_idx += 1
            else: break
        if r_idx not in lanes: lanes[r_idx] = set()
        lanes[r_idx].update(seg_dates)
        for i, rec in enumerate(seg['records']):
            layout_map[(rec['date'], r_idx)] = {'rec': rec, 'is_start': i==0, 'is_end': i==len(seg['records'])-1, 'duration': len(seg['records'])}
    return layout_map, (max(lanes.keys()) + 1 if lanes else 0)

def get_stats_optimized(date_str, all_drivers_df, today_sch, history_dict):
    # (기존 통계 로직 유지)
    return "", ""

def get_streak_info(full_schedule_map, p_name, p_date_str, p_type):
    # (기존 스트릭 로직 유지)
    return "", "", ""

# ==========================================
# 5. 화면 렌더링 (핵심 수정 적용)
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; }
        .calendar-day-box { 
            border: 1px solid #e9ecef; min-height: 200px; padding: 0; 
            background-color: white; display: flex; flex-direction: column; height: auto !important; 
        }
        .calendar-day-box-horiz { flex: 0 0 90px; } 
        .calendar-day-box-grid { width: 100%; margin: 2px; }
        .schedule-bar { font-size: 11px; color: white; margin-bottom: 1px; height: 34px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; }
        .bar-start { border-radius: 4px 0 0 4px; margin-right: -10px !important; margin-left: 2px; z-index: 2; }
        .bar-mid { margin-left: -10px !important; margin-right: -10px !important; z-index: 1; }
        .bar-end { border-radius: 0 4px 4px 0; margin-left: -10px !important; margin-right: 2px; z-index: 2; }
        .bar-single { border-radius: 4px; margin: 0 2px 1px 2px; z-index: 3; }
        /* 버튼 스타일 */
        button[kind="primary"] { background-color: #00592D !important; border-color: #00592D !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

def render_calendar_tab():
    if st.session_state.get('last_error_msg'): st.error("오류 발생"); st.code(st.session_state['last_error_msg'])
    _render_calendar_tab_unsafe()

def _render_calendar_tab_unsafe():
    c_title, c_legend, c_view = st.columns([1, 1.5, 0.8])
    with c_title: st.markdown("### 📅 월간 휴무 신청 현황")
    with c_legend:
        types = ["휴무", "교육", "경조사", "징계", "당일 해지", "병가", "휴직", "기타"]
        html = "<div style='display:flex; flex-wrap:wrap; gap:5px; margin-top:10px;'>"
        for t in types: html += f"<span style='background:{get_type_color(t)}; color:white; padding:2px 8px; border-radius:12px; font-size:11px;'>{t}</span>"
        st.markdown(html+"</div>", unsafe_allow_html=True)
    with c_view: view_mode = st.radio("보기", ["가로 스크롤", "달력"], horizontal=True, label_visibility="collapsed")
    
    inject_custom_css()
    now = get_kst_now()
    if 'view_year' not in st.session_state: st.session_state.view_year = now.year
    if 'view_month' not in st.session_state: st.session_state.view_month = now.month
    
    c1, c2, c3, c4, c5, c6 = st.columns([0.3, 0.7, 0.3, 0.7, 0.4, 0.4])
    with c1: st.write("년도:")
    with c2: 
        if st.selectbox("년도", range(2023, now.year+3), key='sb_view_year') != st.session_state.view_year:
            st.session_state.view_year = st.session_state.sb_view_year; st.rerun()
    with c3: st.write("월:")
    with c4: 
        if st.selectbox("월", range(1, 13), key='sb_view_month') != st.session_state.view_month:
            st.session_state.view_month = st.session_state.sb_view_month; st.rerun()
    with c5: st.button("◀", on_click=prev_cal_callback)
    with c6: st.button("▶", on_click=next_cal_callback)
    st.divider()

    year, month = st.session_state.view_year, st.session_state.view_month
    
    # [수정 1] 데이터 로딩 및 날짜 형식 강력 표준화
    df = load_data("schedules")
    if not df.empty and 'date' in df.columns:
        # errors='coerce'로 변환 안되는 데이터는 NaT로 처리 후, 유효한 날짜만 YYYY-MM-DD로 변환
        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime("%Y-%m-%d")
        # 혹시 변환 실패한 행(NaT) 제거
        df = df.dropna(subset=['date'])
        if 'name' in df.columns: df['name'] = df['name'].astype(str).str.strip()
    
    # 필터링
    df_month = df[df['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df.empty else pd.DataFrame()
    
    full_schedule_map = {}
    if not df.empty:
        for _, row in df.iterrows(): full_schedule_map[(row['name'], str(row['date']))] = row['type']
        
    df_events = load_data("company_events") # 이벤트도 동일하게 처리 가능하나 생략
    if not df_events.empty and 'date' in df_events.columns:
         df_events['date'] = pd.to_datetime(df_events['date'], errors='coerce').dt.strftime("%Y-%m-%d")
    df_events_month = df_events[df_events['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df_events.empty else pd.DataFrame()

    all_drivers = load_data("drivers")
    # (그룹 히스토리 로딩 - 생략)
    group_history_df = load_data("group_history")
    history_dict = {}
    if not group_history_df.empty:
        for _, row in group_history_df.iterrows():
            if row['driver_name'] not in history_dict: history_dict[row['driver_name']] = []
            history_dict[row['driver_name']].append((row['start_date'], row['group_name']))
        for k in history_dict: history_dict[k].sort(key=lambda x:x[0], reverse=True)

    _, last_day = calendar.monthrange(year, month)
    today_str = now.strftime("%Y-%m-%d")
    tmr_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    def get_day_html(day, is_horiz=True):
        d_str = f"{year}-{month:02d}-{day:02d}"
        wd_idx = datetime(year, month, day).weekday()
        
        today_sch = df_month[df_month['date'] == d_str] if not df_month.empty else pd.DataFrame()
        today_evt = df_events_month[df_events_month['date'] == d_str] if not df_events_month.empty else pd.DataFrame()
        
        # [수정 2] 하이라이트 로직 강화 (!important 추가 및 변수 직접 비교)
        box_style = "background-color: white;"
        if d_str == today_str:
            box_style = "box-shadow: inset 0 0 0 2px #fbc02d !important; background-color: #fff9c4 !important;"
        elif d_str == tmr_str:
            box_style = "box-shadow: inset 0 0 0 1px #ef5350 !important; background-color: #ffebee !important;"
            
        day_color = "#d32f2f" if wd_idx==6 or is_holiday(datetime(year,month,day)) else "#1976D2" if wd_idx==5 else "#333"
        
        html = f'<div class="calendar-day-box {"calendar-day-box-horiz" if is_horiz else "calendar-day-box-grid"}" style="{box_style}">'
        html += f'<div class="day-header" style="background-color:transparent;"><div style="display:flex; justify-content:space-between; padding:0 3px;"><span style="font-weight:bold; color:{day_color};">{day}일({WEEKDAY_KOREAN[wd_idx]})</span><span style="font-size:11px;">{len(today_sch)}명</span></div>'
        html += f'<div class="group-info-box">{get_daily_shift_summary(d_str)}</div></div>'
        
        html += '<div class="event-container">'
        if not today_evt.empty:
            for _, e in today_evt.iterrows(): html += f"<div style='background:#E3F2FD; color:#1565C0; font-size:10px; text-align:center;'>{e['title']}</div>"
        
        if not is_horiz and not today_sch.empty:
            today_sch['rank'] = today_sch['type'].map(lambda x: SORT_ORDER.get(x, 99))
            for _, row in today_sch.sort_values(by=['rank', 'name']).iterrows():
                col = get_type_color(row['type'])
                pre, suf, p_txt = get_streak_info(full_schedule_map, row['name'], d_str, row['type'])
                inner = f"<div style='display:flex; justify-content:center;'>{pre} {row['name']} {suf}</div>"
                n_txt = (row['note'] or row['type']) + (f" {p_txt}" if p_txt else "")
                html += f"<div class='schedule-bar bar-single' style='background:{col}; border:1px solid #333;' title='{n_txt}'>{inner}<div style='font-size:9px;'>{n_txt}</div></div>"
        html += '</div></div>'
        return html

    if "가로" in view_mode:
        l_map, m_row = calculate_layout_rows(df_month)
        h_html = '<div class="horizontal-scroll-container">'
        for d in range(1, last_day+1):
            d_str = f"{year}-{month:02d}-{d:02d}"
            h_html += get_day_html(d, True)[:-6] # 닫는 div 하나 제거해서 아래 내용 추가
            for r in range(m_row):
                if (d_str, r) in l_map:
                    it = l_map[(d_str, r)]
                    row = it['rec']
                    col = get_type_color(row['type'])
                    pre, suf, p_txt = get_streak_info(full_schedule_map, row['name'], d_str, row['type'])
                    
                    cls = "bar-single"
                    bst = "border:1px solid #333;"
                    if it['duration'] >= 2:
                        if it['is_start']: cls = "bar-start"; bst="border:1px solid #333; border-right:none;"
                        elif it['is_end']: cls = "bar-end"; bst="border:1px solid #333; border-left:none;"
                        else: cls = "bar-mid"; bst="border-top:1px solid #333; border-bottom:1px solid #333;"
                    
                    inner = f"{pre} {row['name']} {suf}"
                    h_html += f"<div class='schedule-bar {cls}' style='background:{col}; {bst}'>{inner}</div>"
                else: h_html += "<div class='schedule-spacer'></div>"
            h_html += "</div></div>" # 닫는 div 복구
        st.markdown(h_html+"</div>", unsafe_allow_html=True)
    else:
        cols = st.columns(7)
        for i, w in enumerate(WEEKDAY_KOREAN): cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:{'#d32f2f' if i==6 else '#1976D2' if i==5 else 'black'};'>{w}</div>", unsafe_allow_html=True)
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, d in enumerate(week):
                with cols[i]:
                    if d == 0: st.markdown("<div class='calendar-day-box' style='background:#f8f9fa;'></div>", unsafe_allow_html=True)
                    else: st.markdown(get_day_html(d, False), unsafe_allow_html=True)

# (나머지 탭 렌더링 함수들 - 기존 코드 유지, render_individual_calendar_tab 등도 위와 같이 날짜 파싱 추가 권장)
def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황")
    drivers = load_data("drivers")
    if drivers.empty: st.warning("승무원 데이터 없음"); return
    
    # 여기도 날짜 정규화 적용
    df_plan = load_data("schedules")
    if not df_plan.empty and 'date' in df_plan.columns:
        df_plan['date'] = pd.to_datetime(df_plan['date'], errors='coerce').dt.strftime("%Y-%m-%d")
        if 'name' in df_plan.columns: df_plan['name'] = df_plan['name'].astype(str).str.strip()
    
    # ... (나머지 로직 동일) ...
    # 실제 코드 합칠 때는 이전 답변의 render_individual_calendar_tab 전체를 쓰되 
    # 위 날짜 정규화 부분만 교체해서 넣으세요.

# (메인 함수 및 기타 탭 함수들 유지)
def main():
    st.set_page_config(page_title="우진교통 배차 관리", layout="wide")
    if 'auth_status' not in st.session_state: st.session_state['auth_status'] = None
    if st.session_state['auth_status'] is None:
        c1,c2,c3 = st.columns(3)
        with c2:
            st.title("로그인")
            uid = st.text_input("ID"); upw = st.text_input("PW", type="password")
            if st.button("Login", type="primary"):
                user = login_user(uid, upw)
                if user: st.session_state['auth_status']=user[0]; st.session_state['user_name']=user[1]; st.rerun()
                else: st.error("실패")
        return

    st.sidebar.title(f"{st.session_state['user_name']}님")
    if st.sidebar.button("로그아웃"): st.session_state['auth_status']=None; st.rerun()
    
    tabs = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력", "⚙️ 관리", "📊 조회", "🔧 로그"])
    with tabs[0]: render_calendar_tab()
    # 나머지 탭 연결... (생략된 부분은 기존 코드 사용)

if __name__ == '__main__':
    main()
