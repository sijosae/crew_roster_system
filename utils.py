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
        "실제근무_본인": "#1e88e5",
        "실제근무_대운": "#8e24aa",
        "감차휴무": "#00592D"
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
# 3. 데이터 저장 및 관리 함수 (절대 좌표 강제)
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
            rows_to_add.append([str(row_id), str(name), str(d_str), str(type), str(note), str(created_at), str(shift)])
            count += 1
            
    if rows_to_add:
        sh = get_db_connection()
        ws = sh.worksheet("schedules")
        
        existing_data = ws.get_all_values()
        next_row = len(existing_data) + 1
        
        try:
            ws.update(values=rows_to_add, range_name=f"A{next_row}", value_input_option='USER_ENTERED')
        except TypeError:
            ws.update(f"A{next_row}", rows_to_add, value_input_option='USER_ENTERED')
            
        clear_cache_after_save()
    return len(rows_to_add), generated_ids

def add_company_event(date, title):
    sh = get_db_connection()
    ws = sh.worksheet("company_events")
    now_kst = get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d")
    row_id = now_kst.strftime("%y%m%d%H%M%S")
    
    existing_data = ws.get_all_values()
    next_row = len(existing_data) + 1
    
    data = [[str(row_id), str(date), str(title), str(created_at)]]
    try:
        ws.update(values=data, range_name=f"A{next_row}", value_input_option='USER_ENTERED')
    except TypeError:
