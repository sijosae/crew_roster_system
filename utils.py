import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar
import hashlib
import secrets
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
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
        .block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; padding-left: 1rem !important; padding-right: 0.5rem !important; max-width: 100% !important; }
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
        button[kind="primary"], div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button { background-color: #00592D !important; border-color: #00592D !important; color: white !important; }
        button[kind="primary"]:hover, div[data-testid="stButton"] button:hover, div[data-testid="stFormSubmitButton"] button:hover { background-color: #004d26 !important; border-color: #004d26 !important; color: white !important; }
        @media (max-width: 640px) { h1 { font-size: 1.6rem !important; } .mobile-font { font-size: 10px !important; } .mobile-header { font-size: 11px !important; } }

        /* [상위 탭] 진짜 st.tabs()로 만든 메인 탭(휴무 현황/근무 현황/...)을 서브메뉴보다 눈에 띄게 */
        [data-testid="stTab"] p { font-size: 16px !important; font-weight: 700 !important; }
        /* 탭 내용이 탭 바로 바로 아래 붙도록 위쪽 여백 축소 (서브메뉴가 상위 탭이랑 너무 떨어져 보이던 것) */
        [data-testid="stTabContent"] { padding-top: 0.4rem !important; }

        /* [서브메뉴 공통] utils.render_submenu()가 만드는 키(submenu_*_btn_*)는 전부 이 스타일을 씀.
           키가 버튼(<button>) 자신이 아니라 그 조상 div에 붙어서 자손 선택자를 쓰고, 명시도를
           위 전역 버튼 스타일(!important)보다 높이려고 조상 클래스를 같이 넣음. */
        div[class*="st-key-submenu_"] div[data-testid="stButton"] button,
        div[class*="st-key-submenu_"] div[data-testid="stButton"] button:hover,
        div[class*="st-key-submenu_"] div[data-testid="stButton"] button:focus,
        div[class*="st-key-submenu_"] div[data-testid="stButton"] button:active {
            background: transparent !important;
            border: none !important;
            border-bottom: 2px solid transparent !important;
            box-shadow: none !important;
            padding: 0 8px 4px 8px !important;
            border-radius: 0 !important;
            color: #888 !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            min-height: 0 !important;
            height: auto !important;
            width: auto !important;
        }
        /* 서브메뉴 버튼이 칸을 꽉 채우지 않고 글자 크기만큼만 차지하도록 컬럼을 shrink-to-fit
           (Streamlit 컬럼의 실제 data-testid는 "stColumn"임 - "column"이 아님, 테스트 앱으로 확인함) */
        div[class*="st-key-submenu_"] div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            gap: 4px !important;
            justify-content: flex-start !important;
        }
        div[class*="st-key-submenu_"] div[data-testid="stColumn"] {
            width: auto !important; min-width: 0 !important; flex: 0 0 auto !important;
        }

        /* [월 이동 묶음] utils.render_month_nav()가 만드는 monthnav_ 컨테이너: 화면이 좁아져도
           줄바꿈 대신 가로 스크롤로 빠짐. ◀▶ 버튼은 34px 고정, 가운데 셀렉트박스가 나머지를 채움.
           [중요] 모바일(좁은 화면)에서는 Streamlit이 각 stColumn에 자체적으로 width:100%에
           가까운 반응형 규칙을 걸어서(컬럼을 세로로 쌓으려고) desktop에서 잘 먹던 비율 기반
           크기가 무시되고 3칸이 전부 꽉 차려고 해서 서로 겹쳐 튀어나갔음(실제 375px 모바일
           화면으로 재현/확인함). 그래서 1번째/3번째 컬럼(버튼)은 폭을 직접 고정하고,
           2번째 컬럼(셀렉트박스)만 남는 공간을 갖게 nth-child로 명시적으로 강제함. */
        div[class*="st-key-monthnav_"] {
            overflow-x: auto !important;
            max-width: 100% !important;
        }
        div[class*="st-key-monthnav_"] div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            gap: 4px !important;
            width: 100% !important;
        }
        div[class*="st-key-monthnav_"] div[data-testid="stColumn"]:nth-of-type(1),
        div[class*="st-key-monthnav_"] div[data-testid="stColumn"]:nth-of-type(3) {
            width: 38px !important; min-width: 38px !important; max-width: 38px !important;
            flex: 0 0 38px !important;
        }
        div[class*="st-key-monthnav_"] div[data-testid="stColumn"]:nth-of-type(2) {
            width: auto !important; min-width: 0 !important; flex: 1 1 auto !important;
        }
        div[class*="st-key-monthnav_"] div[data-testid="stButton"] button {
            width: 34px !important; min-width: 34px !important; max-width: 34px !important;
            padding: 0.2rem 0 !important;
            font-size: 12px !important;
        }

        /* [전체화면 로딩 오버레이] st.spinner()를 화면 전체가 어두워지며 중앙에 뜨는 형태로 변경 */
        div[data-testid="stSpinner"] {
            position: fixed !important;
            inset: 0 !important;
            width: 100vw !important; height: 100vh !important;
            background: rgba(0,0,0,0.45);
            z-index: 99999 !important;
            display: flex !important;
            align-items: center; justify-content: center;
        }
        div[data-testid="stSpinner"] > div {
            background: white;
            padding: 24px 36px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.35);
            font-size: 16px;
            font-weight: bold;
            width: fit-content !important;
            max-width: 90vw;
            flex: 0 0 auto !important;
        }
    </style>
    """, unsafe_allow_html=True)

# [공용 UI] 텍스트 링크 스타일의 서브메뉴. 탭(st.tabs) 안에 또 탭을 넣으면 화면이 중구난방이라,
# 어디서 쓰든 똑같이 생기게 이 함수 하나로 통일함. 기본 스타일은 inject_custom_css()에 정의돼
# 있고, 여기서는 "지금 선택된 항목"에만 초록 밑줄을 얹는 부분만 처리함.
def render_submenu(options, key_prefix, default_index=0):
    state_key = f"{key_prefix}_active"
    if state_key not in st.session_state:
        st.session_state[state_key] = options[default_index]
    if st.session_state[state_key] not in options:
        st.session_state[state_key] = options[default_index]

    with st.container(key=f"submenu_{key_prefix}"):
        cols = st.columns(len(options) + 1)
        for i, opt in enumerate(options):
            with cols[i]:
                if st.button(opt, key=f"{key_prefix}_btn_{i}"):
                    st.session_state[state_key] = opt
                    st.rerun(scope="fragment")

    active = st.session_state[state_key]
    active_idx = options.index(active)
    st.markdown(f"""
    <style>
    .st-key-{key_prefix}_btn_{active_idx} div[data-testid="stButton"] button,
    .st-key-{key_prefix}_btn_{active_idx} div[data-testid="stButton"] button:hover,
    .st-key-{key_prefix}_btn_{active_idx} div[data-testid="stButton"] button:focus,
    .st-key-{key_prefix}_btn_{active_idx} div[data-testid="stButton"] button:active {{
        color: #00592D !important;
        border-bottom: 2px solid #00592D !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    return active

# [공용 UI] "년도(select) / (◀)(월 select)(▶)" 조합. 모든 탭에서 똑같은 모양으로 쓰려고
# 하나로 뺌. 세 개(◀,월,▶)는 모바일에서도 줄바꿈 안 되게 monthnav_ 컨테이너로 묶음.
# year_state_key/month_state_key: st.session_state에 이미 있는 현재 년/월 값 키.
def render_month_nav(key_prefix, year_state_key, month_state_key, min_year=2023, year_span=3):
    now = get_kst_now()
    cur_year = st.session_state[year_state_key]
    cur_month = st.session_state[month_state_key]

    # [월 단위 선택] Streamlit엔 월 전용 피커가 없어서(date_input은 항상 일까지 나옴),
    # "2026년 08월"처럼 월 단위로 이미 묶인 항목을 셀렉트박스 하나로 고르게 함.
    options = [(y, m) for y in range(min_year, now.year + year_span + 1) for m in range(1, 13)]
    ym_key = f"{key_prefix}_ym_sel"

    # [중요] 버튼(◀▶)이 session_state의 년/월만 바꾸고 셀렉트박스 자기 자신의 위젯 상태는
    # 그대로 두면, 다음 줄의 "index=idx"는 무시되고(이미 키가 있는 위젯이라) 예전 값 그대로
    # 남아있는 셀렉트박스 값이 "사용자가 바꾼 값"으로 오인되어 버튼이 바꾼 값을 도로 덮어씀.
    # 그래서 버튼 콜백에서 셀렉트박스의 위젯 상태(ym_key)도 같이 맞춰줘야 함.
    def _prev():
        y, m = st.session_state[year_state_key], st.session_state[month_state_key]
        if m == 1: y, m = y - 1, 12
        else: m = m - 1
        st.session_state[year_state_key] = y
        st.session_state[month_state_key] = m
        st.session_state[ym_key] = (y, m)

    def _next():
        y, m = st.session_state[year_state_key], st.session_state[month_state_key]
        if m == 12: y, m = y + 1, 1
        else: m = m + 1
        st.session_state[year_state_key] = y
        st.session_state[month_state_key] = m
        st.session_state[ym_key] = (y, m)

    with st.container(key=f"monthnav_{key_prefix}"):
        c_prev, c_pick, c_next = st.columns([0.15, 1, 0.15])
        with c_prev:
            st.button("◀", key=f"{key_prefix}_prev", on_click=_prev)
        with c_pick:
            idx = options.index((cur_year, cur_month)) if (cur_year, cur_month) in options else 0
            picked = st.selectbox(
                "년월 선택", options, index=idx, format_func=lambda ym: f"{ym[0]}년 {ym[1]}월",
                key=ym_key, label_visibility="collapsed"
            )
        with c_next:
            st.button("▶", key=f"{key_prefix}_next", on_click=_next)

    if picked != (st.session_state[year_state_key], st.session_state[month_state_key]):
        st.session_state[year_state_key] = picked[0]
        st.session_state[month_state_key] = picked[1]
        st.rerun(scope="fragment")

# ==========================================
# 2. DB 연결 및 데이터 로드
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
        # secrets에 spreadsheet_id가 있으면(로컬 개발용 사본) ID로, 없으면(운영) 이름으로 찾음
        spreadsheet_id = st.secrets.get("spreadsheet_id")
        if spreadsheet_id:
            sh = client.open_by_key(spreadsheet_id)
        else:
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

def clear_cache_after_save(sheet_name=None):
    if sheet_name is None:
        st.cache_data.clear()
    elif isinstance(sheet_name, (list, tuple)):
        for s in sheet_name:
            load_data.clear(s)
    else:
        load_data.clear(sheet_name)

# ==========================================
# 2-1. 감사 로그(작업 이력) + 롤백
# ==========================================
# [추가] 로그인 상태에서 일어나는 생성/삭제/수정을 전부 별도 시트(audit_log)에 기록하고,
# 각 기록마다 반대 동작을 실행해서 되돌릴 수 있게 함. action은 화면/기능별로 구체적인
# 태그를 쓰고(schedule_create 등), 롤백은 그 태그에 맞는 "반대 동작"을 직접 호출하는
# 방식으로 만듦 - 시트마다 식별 방식이 다 달라서(schedules는 id 컬럼, drivers/users는
# 이름) 하나의 범용 로직으로 억지로 묶는 것보다 훨씬 안전함.
AUDIT_LOG_SHEET = "audit_log"
AUDIT_LOG_HEADERS = ['id', 'timestamp', 'username', 'action', 'summary', 'before', 'after', 'rolled_back']
AUDIT_LOG_RETENTION_DAYS = 30

def _get_or_create_ws(sheet_name, headers):
    sh = get_db_connection()
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=2000, cols=len(headers))
        ws.append_row(headers)
    return ws

# [추가] 작업 로그가 계속 쌓이면 조회가 느려지므로, 오래된 기록을 정리함.
# 서버에 상시 실행되는 스케줄러가 없는 구조(요청 올 때만 깨어남)라서, 대신
# st.cache_resource(ttl=86400)로 "하루에 한 번만 실제로 실행"되게 함 - 여러 세션/사용자가
# 계속 호출해도 캐시가 안 끝난 동안은 그냥 캐시된 값만 반환하고 실제 정리는 스킵됨.
def _cleanup_old_audit_log():
    try:
        ws = _get_or_create_ws(AUDIT_LOG_SHEET, AUDIT_LOG_HEADERS)
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return
        headers = all_values[0]
        ts_idx = headers.index('timestamp') if 'timestamp' in headers else 1
        cutoff = get_kst_now() - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
        kept_rows = []
        removed = 0
        for row in all_values[1:]:
            keep = True
            if len(row) > ts_idx and row[ts_idx]:
                try:
                    if datetime.strptime(row[ts_idx], "%Y-%m-%d %H:%M:%S") < cutoff:
                        keep = False
                except ValueError:
                    pass
            if keep:
                kept_rows.append(row)
            else:
                removed += 1
        if removed == 0:
            return
        ws.clear()
        all_new = [headers] + kept_rows
        try:
            ws.update(values=all_new, range_name="A1", value_input_option='USER_ENTERED')
        except TypeError:
            ws.update("A1", all_new, value_input_option='USER_ENTERED')
        clear_cache_after_save(AUDIT_LOG_SHEET)
    except Exception:
        pass

@st.cache_resource(ttl=86400)
def _audit_log_cleanup_gate():
    _cleanup_old_audit_log()
    return True

def record_audit(action, summary, before=None, after=None):
    # 감사 로그 기록 자체가 실패해도 실제 작업(저장/삭제)까지 막으면 안 되므로 조용히 넘어감
    try:
        _audit_log_cleanup_gate()
        ws = _get_or_create_ws(AUDIT_LOG_SHEET, AUDIT_LOG_HEADERS)
        entry_id = get_kst_now().strftime("%y%m%d%H%M%S%f")[:-3]
        username = st.session_state.get('user_name', '') or st.session_state.get('auth_status', 'unknown')
        row = [
            entry_id, get_kst_now().strftime("%Y-%m-%d %H:%M:%S"), username, action, summary,
            json.dumps(before, ensure_ascii=False) if before is not None else "",
            json.dumps(after, ensure_ascii=False) if after is not None else "",
            ""
        ]
        ws.append_row(row, value_input_option='USER_ENTERED')
        clear_cache_after_save(AUDIT_LOG_SHEET)
        return entry_id
    except Exception:
        return None

def get_audit_log():
    _audit_log_cleanup_gate()
    return load_data(AUDIT_LOG_SHEET)

# [추가] 감사 로그가 대부분 승무원+일정에 대한 기록이라, before/after에 저장해둔 원본
# 행 데이터에서 승무원 이름/일자를 뽑아 로그 목록에 별도 컬럼으로 보여주기 위함.
def summarize_audit_entry(before_json, after_json):
    try:
        rows = json.loads(after_json) if after_json else (json.loads(before_json) if before_json else [])
    except (json.JSONDecodeError, TypeError):
        rows = []
    if not rows:
        return "-", "-"
    names, dates = [], []
    for r in rows:
        n = r.get('name')
        d = r.get('date')
        if n and n not in names: names.append(n)
        if d and d not in dates: dates.append(d)
    dates.sort()
    if not names:
        name_disp = "-"
    elif len(names) == 1:
        name_disp = names[0]
    else:
        name_disp = f"{names[0]} 외 {len(names) - 1}명"
    if not dates:
        date_disp = "-"
    elif len(dates) == 1:
        date_disp = dates[0]
    else:
        date_disp = f"{dates[0]} ~ {dates[-1]}"
    return name_disp, date_disp

def _mark_rolled_back(entry_id):
    try:
        ws = _get_or_create_ws(AUDIT_LOG_SHEET, AUDIT_LOG_HEADERS)
        col_values = ws.col_values(1)
        row_idx = col_values.index(entry_id) + 1
        ws.update_cell(row_idx, AUDIT_LOG_HEADERS.index('rolled_back') + 1, "Y")
        clear_cache_after_save(AUDIT_LOG_SHEET)
    except (ValueError, gspread.exceptions.WorksheetNotFound):
        pass

def rollback_audit_entry(entry_id):
    df = get_audit_log()
    if df.empty or 'id' not in df.columns:
        return False, "감사 로그가 없습니다."
    match = df[df['id'] == entry_id]
    if match.empty:
        return False, "해당 기록을 찾을 수 없습니다."
    entry = match.iloc[0]
    if str(entry.get('rolled_back', '')).strip().upper() == 'Y':
        return False, "이미 롤백된 작업입니다."

    action = entry['action']
    before = json.loads(entry['before']) if entry.get('before') else None
    after = json.loads(entry['after']) if entry.get('after') else None

    try:
        if action == 'schedule_create':
            delete_rows_by_ids("schedules", [r['id'] for r in after], _skip_audit=True)
        elif action == 'schedule_delete':
            _restore_rows("schedules", before)
        elif action == 'schedule_update':
            _overwrite_row("schedules", before[0])
        elif action == 'event_create':
            delete_rows_by_ids("company_events", [r['id'] for r in after], _skip_audit=True)
        elif action == 'driver_create':
            delete_driver(after[0]['id'], _skip_audit=True)
        elif action == 'driver_resign':
            set_driver_resignation(before[0]['id'], before[0].get('resigned_date', ''), _skip_audit=True)
        elif action == 'driver_delete':
            _restore_driver_full(before)
        elif action == 'user_create':
            delete_user_account(after[0]['username'], _skip_audit=True)
        elif action == 'user_delete':
            _restore_rows("users", before)
        else:
            return False, "이 작업 유형은 롤백을 지원하지 않습니다."
    except Exception as e:
        return False, f"롤백 실패: {e}"

    _mark_rolled_back(entry_id)
    record_audit("rollback", f"[{entry_id}] {entry.get('summary','')} 롤백")
    return True, "롤백되었습니다."

def _restore_rows(sheet_name, rows):
    if not rows: return
    sh = get_db_connection()
    ws = sh.worksheet(sheet_name)
    headers = ws.row_values(1)
    values = [[r.get(h, "") for h in headers] for r in rows]
    ws.append_rows(values, value_input_option='USER_ENTERED')
    clear_cache_after_save(sheet_name)

def _overwrite_row(sheet_name, row_dict):
    if not row_dict: return
    sh = get_db_connection()
    ws = sh.worksheet(sheet_name)
    headers = ws.row_values(1)
    col_values = ws.col_values(1)
    try:
        row_idx = col_values.index(str(row_dict.get(headers[0], ''))) + 1
    except ValueError:
        return
    values = [row_dict.get(h, "") for h in headers]
    ws.update(values=[values], range_name=f"A{row_idx}")
    clear_cache_after_save(sheet_name)

def _restore_driver_full(before_rows):
    # before_rows: delete_driver 롤백용. drivers 시트 1행 + group_history/schedules 여러 행이
    # 섞여서 들어옴(각 행에 __sheet 키로 원래 시트 이름을 같이 저장해둠 - delete_driver 참고)
    by_sheet = {}
    for r in before_rows:
        sheet = r.get('__sheet')
        row = {k: v for k, v in r.items() if k != '__sheet'}
        by_sheet.setdefault(sheet, []).append(row)
    for sheet_name, rows in by_sheet.items():
        _restore_rows(sheet_name, rows)

# ==========================================
# 3. 데이터 저장 (절대 좌표 강제)
# ==========================================
# [추가] 휴무 등록 시 오타 등으로 실제 등록 안 된 승무원 이름이 그대로 저장되는 걸 막기 위한 검증.
# schedules에 이름만 잘못 들어가면 개인현황(등록된 승무원만 목록에 뜸)에서 찾을 방법이 없어져서
# 저장 전에 미리 걸러내야 함.
def validate_driver_names(name_list):
    drivers_df = load_data("drivers")
    valid_names = set(drivers_df['name'].astype(str).str.strip()) if not drivers_df.empty else set()
    return [n for n in name_list if n not in valid_names]

# [추가] 같은 사람이 같은 날짜에 이미 휴무 등록이 되어있는데 또 등록되는 걸 막기 위한 검증.
# (겹치는 (이름, 날짜) 목록을 반환 - 비어있으면 중복 없음)
def check_duplicate_schedule(name_list, start, end):
    df = load_data("schedules")
    if df.empty:
        return []
    dates = pd.date_range(start, end)
    date_strs = set(d.strftime("%Y-%m-%d") for d in dates)
    name_set = set(name_list)
    dup_df = df[df['name'].isin(name_set) & df['date'].astype(str).isin(date_strs)]
    return [(row['name'], row['date']) for _, row in dup_df.iterrows()]

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
        ws.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        clear_cache_after_save("schedules")
        headers = ['id', 'name', 'date', 'type', 'note', 'created_at', 'shift']
        after_rows = [dict(zip(headers, r)) for r in rows_to_add]
        record_audit("schedule_create", f"{len(name_list)}명 일정 등록 ({type})", after=after_rows)
    return len(rows_to_add), generated_ids

def add_company_event(date, title):
    sh = get_db_connection()
    ws = sh.worksheet("company_events")
    now_kst = get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d")
    row_id = now_kst.strftime("%y%m%d%H%M%S")
    data = [[str(row_id), str(date), str(title), str(created_at)]]
    ws.append_rows(data, value_input_option='USER_ENTERED')
    clear_cache_after_save("company_events")
    record_audit("event_create", f"행사 등록: {title}",
                  after=[{'id': row_id, 'date': str(date), 'title': str(title), 'created_at': created_at}])
    return row_id

def delete_rows_by_ids(sheet_name, id_list, _skip_audit=False):
    if not id_list: return False
    sh = get_db_connection()
    ws = sh.worksheet(sheet_name)
    all_values = ws.get_all_values()
    if not all_values: return False
    headers = all_values[0]
    col_values = [row[0] if row else "" for row in all_values]
    id_set = set(str(i) for i in id_list)
    before_rows = [dict(zip(headers, row)) for row in all_values[1:] if row and row[0] in id_set]

    rows_to_delete = []
    for target_id in id_list:
        try:
            row_idx = col_values.index(target_id) + 1
            rows_to_delete.append(row_idx)
        except ValueError: continue
    rows_to_delete.sort(reverse=True)
    for r_idx in rows_to_delete:
        ws.delete_rows(r_idx)
    clear_cache_after_save(sheet_name)
    if not _skip_audit and before_rows:
        action = "schedule_delete" if sheet_name == "schedules" else f"{sheet_name}_rows_delete"
        record_audit(action, f"{sheet_name} {len(before_rows)}건 삭제", before=before_rows)
    return True

# [추가] 휴무 현황 > 개인 현황 목록에서 일정 항목 수정용.
# schedules 시트 컬럼 순서: id(A), name(B), date(C), type(D), note(E), created_at(F), shift(G)
def update_schedule_event(row_id, date_str, type_str, shift, note, _skip_audit=False):
    sh = get_db_connection()
    ws = sh.worksheet("schedules")
    all_values = ws.get_all_values()
    if not all_values: return False
    headers = all_values[0]
    col_values = [row[0] if row else "" for row in all_values]
    try:
        row_idx = col_values.index(str(row_id)) + 1
    except ValueError:
        return False
    before_row = dict(zip(headers, all_values[row_idx - 1]))

    ws.update_cell(row_idx, 3, str(date_str))
    ws.update_cell(row_idx, 4, str(type_str))
    ws.update_cell(row_idx, 5, str(note))
    ws.update_cell(row_idx, 7, str(shift))
    clear_cache_after_save("schedules")

    if not _skip_audit:
        after_row = dict(before_row)
        after_row.update({'date': str(date_str), 'type': str(type_str), 'note': str(note), 'shift': str(shift)})
        record_audit("schedule_update", f"{before_row.get('name','')} 일정 수정", before=[before_row], after=[after_row])
    return True

WORK_HISTORY_REQUIRED_COLS = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at']

def work_history_sheet_name(year):
    return f"work_history_{int(year)}"

# [연도별 분리] work_history가 25만 행까지 커지면서 매번 전체를 읽는 비용이 커져
# 연도별 시트(work_history_2026 등)로 나눔. 이 앱의 모든 조회는 이미 "선택된 연도" 하나만
# 다루므로(개인별/연간집계/차량별현황), 연도 시트 하나만 읽으면 충분함.
def load_work_history_for_year(year):
    return load_data(work_history_sheet_name(year))

def _save_work_history_year_group(year, df_new_year):
    sheet_name = work_history_sheet_name(year)
    sh = get_db_connection()
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
        ws.append_row(WORK_HISTORY_REQUIRED_COLS)

    existing_data = ws.get_all_values()
    df_old = pd.DataFrame()
    if len(existing_data) > 1:
        headers = existing_data.pop(0)
        df_old = pd.DataFrame(existing_data, columns=headers)

    for c in WORK_HISTORY_REQUIRED_COLS:
        if c not in df_new_year.columns: df_new_year[c] = ""
        if c not in df_old.columns: df_old[c] = ""
    df_new_year = df_new_year[WORK_HISTORY_REQUIRED_COLS]

    if df_old.empty:
        df_final = df_new_year
    else:
        df_old = df_old[WORK_HISTORY_REQUIRED_COLS]
        df_combined = pd.concat([df_old, df_new_year])
        df_final = df_combined.drop_duplicates(subset=['date', 'name', 'shift'], keep='last')

    df_final = df_final.sort_values(by=['date', 'name'])
    ws.clear()

    header = [WORK_HISTORY_REQUIRED_COLS]
    data_to_write = df_final.fillna("").astype(str).values.tolist()
    all_values = header + data_to_write
    try:
        ws.update(values=all_values, range_name="A1", value_input_option='USER_ENTERED')
    except TypeError:
        ws.update("A1", all_values, value_input_option='USER_ENTERED')
    clear_cache_after_save(sheet_name)
    return len(df_new_year)

def save_work_history(df_new):
    if df_new.empty:
        return 0
    df_new = df_new.copy()
    years = pd.to_datetime(df_new['date'], errors='coerce').dt.year
    saved = 0
    for year in sorted(years.dropna().unique()):
        group = df_new[years == year].copy()
        saved += _save_work_history_year_group(int(year), group)
    return saved

# [마이그레이션] 연도별 분리 전에 쓰던 단일 work_history 시트를 work_history_{year} 시트들로
# 옮기는 1회성 작업. 예전 시트를 찾아서 옮긴 뒤 이름을 바꿔두므로, 다시 실행해도
# (예전 시트가 더 이상 없어서) 아무 일도 안 일어나 안전하게 여러 번 눌러도 됨.
def migrate_old_work_history():
    sh = get_db_connection()
    try:
        ws_old = sh.worksheet("work_history")
    except gspread.exceptions.WorksheetNotFound:
        return {"status": "not_found", "count": 0}

    existing_data = ws_old.get_all_values()
    if len(existing_data) <= 1:
        return {"status": "empty", "count": 0}

    headers = existing_data.pop(0)
    df_old = pd.DataFrame(existing_data, columns=headers)
    saved = save_work_history(df_old)

    ws_old.update_title(f"work_history_migrated_{get_kst_now().strftime('%Y%m%d_%H%M%S')}")
    return {"status": "done", "count": saved}

def _new_driver_id():
    return get_kst_now().strftime("%y%m%d%H%M%S")

def _row_from_headers(headers, values_dict):
    return [str(values_dict.get(h, "")) for h in headers]

def add_driver_with_group(name, group_name, start_date="2020-01-01"):
    # [수정] id 컬럼에 항상 빈 문자열("")을 넣고 있어서 신규 등록자에게 id가 안 붙던 버그.
    # 컬럼 위치도 고정하지 않고 헤더 이름 기준으로 값을 채움(퇴사처리 버그와 같은 이유).
    sh = get_db_connection()
    ws_drivers = sh.worksheet("drivers")
    created_at = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    driver_id = _new_driver_id()
    try:
        existing = ws_drivers.find(name)
        if not existing:
            headers = ws_drivers.row_values(1)
            row = _row_from_headers(headers, {
                'id': driver_id, 'name': name, 'group_name': group_name,
                'created_at': created_at, 'resigned_date': ''
            })
            ws_drivers.append_row(row)
    except: pass
    ws_history = sh.worksheet("group_history")
    ws_history.append_row(["", name, group_name, start_date, created_at])
    clear_cache_after_save(["drivers", "group_history"])
    record_audit("driver_create", f"승무원 등록: {name} ({group_name})",
                  after=[{'id': driver_id, 'name': name, 'group_name': group_name, 'start_date': start_date}])
    return True

# [추가] id 컬럼이 비어있던 예전 등록자들에게 id를 일괄로 부여함 (로그 탭 마이그레이션에서 사용)
def backfill_driver_ids():
    sh = get_db_connection()
    ws = sh.worksheet("drivers")
    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        return 0
    headers = all_values[0]
    try:
        id_col = headers.index('id')
    except ValueError:
        return 0
    updated = 0
    for i, row in enumerate(all_values[1:], start=2):
        cur_id = row[id_col].strip() if len(row) > id_col else ""
        if not cur_id:
            ws.update_cell(i, id_col + 1, f"{_new_driver_id()}{updated:02d}")
            updated += 1
    if updated:
        clear_cache_after_save("drivers")
    return updated

def set_driver_resignation(driver_id, r_date, _skip_audit=False):
    # [수정] 이름으로 찾으면 (1) 컬럼 위치가 밀려있거나 (2) 동명이인/중복 등록이 있을 때
    # 엉뚱한 행을 건드리거나 일부만 처리되는 문제가 있었음. id는 유일하므로 id로 찾도록 바꿈.
    # (컬럼 위치도 헤더 이름 기준으로 찾아서, 실제 시트 구조가 뭐든 안전함)
    sh = get_db_connection()
    ws = sh.worksheet("drivers")
    try:
        all_values = ws.get_all_values()
    except Exception as e:
        return False, f"시트 조회 실패: {e}"
    if not all_values:
        return False, "승무원 시트가 비어있습니다."

    headers = all_values[0]
    try:
        id_col = headers.index('id')
        name_col = headers.index('name')
        resign_col = headers.index('resigned_date')
    except ValueError:
        return False, f"시트 헤더에 id/name/resigned_date 컬럼이 없습니다 (헤더: {headers})."

    row_idx, matched_row = None, None
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) > id_col and row[id_col].strip() == str(driver_id).strip():
            row_idx, matched_row = i, row
            break
    if row_idx is None:
        return False, f"id '{driver_id}'에 해당하는 승무원을 찾을 수 없습니다."

    name = matched_row[name_col].strip() if len(matched_row) > name_col else ""
    before_val = matched_row[resign_col].strip() if len(matched_row) > resign_col else ""

    try:
        ws.update_cell(row_idx, resign_col + 1, r_date)
    except Exception as e:
        return False, f"업데이트 실패: {e}"

    clear_cache_after_save("drivers")
    if not _skip_audit:
        record_audit("driver_resign", f"{name} 퇴사일 설정: {r_date}",
                      before=[{'id': driver_id, 'name': name, 'resigned_date': before_val}],
                      after=[{'id': driver_id, 'name': name, 'resigned_date': r_date}])
    return True, "완료"

def delete_driver(driver_id, _skip_audit=False):
    # [수정] 이름 기준 삭제 -> id 기준 삭제로 변경 (drivers 시트는 id로 정확히 하나만 특정).
    # group_history/schedules는 승무원 id를 안 갖고 있어서(이름만 있음) 이 두 시트는 여전히
    # drivers에서 찾은 이름으로 매칭함 - 대신 get_all_values()로 시트당 한 번만 읽어서
    # find/findall + row_values를 행 개수만큼 부르던 예전 방식보다 훨씬 안전/효율적임.
    sh = get_db_connection()
    before_rows = []

    ws_d = sh.worksheet("drivers")
    driver_name = None
    try:
        all_values = ws_d.get_all_values()
        if all_values:
            headers = all_values[0]
            id_col = headers.index('id') if 'id' in headers else 0
            name_col = headers.index('name') if 'name' in headers else 1
            for idx, row in enumerate(all_values[1:], start=2):
                if len(row) > id_col and row[id_col].strip() == str(driver_id).strip():
                    driver_name = row[name_col].strip() if len(row) > name_col else None
                    row_dict = dict(zip(headers, row))
                    row_dict['__sheet'] = 'drivers'
                    before_rows.append(row_dict)
                    ws_d.delete_rows(idx)
                    break
    except Exception:
        pass

    if driver_name is None:
        return False, f"id '{driver_id}'에 해당하는 승무원을 찾을 수 없습니다."

    def _capture_and_delete(ws, sheet_tag):
        try:
            all_values = ws.get_all_values()
            if not all_values: return
            headers = all_values[0]
            matches = []
            for idx, row in enumerate(all_values[1:], start=2):
                if driver_name in row:
                    row_dict = dict(zip(headers, row))
                    row_dict['__sheet'] = sheet_tag
                    matches.append((idx, row_dict))
            for _, row_dict in matches:
                before_rows.append(row_dict)
            for idx, _ in sorted(matches, key=lambda x: x[0], reverse=True):
                ws.delete_rows(idx)
        except Exception:
            pass

    _capture_and_delete(sh.worksheet("group_history"), 'group_history')
    _capture_and_delete(sh.worksheet("schedules"), 'schedules')

    clear_cache_after_save(["drivers", "group_history", "schedules"])
    if not _skip_audit and before_rows:
        record_audit("driver_delete", f"승무원 삭제: {driver_name}", before=before_rows)
    return True, f"'{driver_name}' 삭제 완료"

def add_user_account(username, password, role, name):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    k_date = get_kst_now().strftime("%Y-%m-%d")
    new_row = [username, make_hash(password), role, name, k_date]
    ws.append_row(new_row)
    clear_cache_after_save("users")
    record_audit("user_create", f"계정 생성: {username} ({name})",
                  after=[{'username': username, 'password': new_row[1], 'role': role, 'name': name, 'created_at': k_date}])
    return True

def delete_user_account(username, _skip_audit=False):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        cell = ws.find(username)
        if cell:
            # [중요] 감사 로그용 이전 값 읽기 실패가 실제 삭제까지 막으면 안 되므로 별도로 감쌈
            before_row = {}
            try:
                headers = ws.row_values(1)
                before_row = dict(zip(headers, ws.row_values(cell.row)))
            except Exception:
                pass
            ws.delete_rows(cell.row)
            clear_cache_after_save("users")
            if not _skip_audit:
                record_audit("user_delete", f"계정 삭제: {username}", before=[before_row] if before_row else None)
    except: pass

def update_user_password(username, new_password):
    sh = get_db_connection()
    ws = sh.worksheet("users")
    try:
        cell = ws.find(username)
        if cell:
            ws.update_cell(cell.row, 2, make_hash(new_password))
            clear_cache_after_save("users")
            record_audit("user_password_update", f"{username} 비밀번호 변경")
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
    clear_cache_after_save("reduction_rules")

# ==========================================
# 4. 날짜 및 스케줄 계산 로직
# ==========================================
def is_holiday(date_obj):
    return date_obj in kr_holidays

def is_holiday_or_weekend(date_obj):
    return date_obj.weekday() >= 5 or date_obj in kr_holidays

def clean_driver_name(name):
    if pd.isna(name): return "" 
    s = str(name).strip()
    if s.lower() == "nan" or s == "": return ""
    s = s.replace("（", "(").replace("）", ")")
    
    # 괄호만 제거
    s_removed = re.sub(r'\(.*?\)', '', s).strip()
    if not s_removed: 
        s_stripped = s.replace("(", "").replace(")", "").strip()
        return s_stripped
    
    return s_removed

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

def normalize_key(val):
    if pd.isna(val) or val == "": return ""
    s = str(val).strip()
    try:
        return str(int(float(s)))
    except:
        return s

def is_reduction_target(date_str, route, seq, rules):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except: return False
    is_holi = is_holiday_or_weekend(d)
    
    tgt_route = normalize_key(route)
    tgt_seq = normalize_key(seq)
    
    for r in rules:
        if r['start'] <= date_str <= r['end']:
            rule_route = normalize_key(r['route'])
            rule_seq = normalize_key(r['seq'])
            
            if rule_route == tgt_route and rule_seq == tgt_seq:
                if r['condition'] == 'Always': return True
                if r['condition'] == 'Weekend/Holiday' and is_holi: return True
    return False

# ==========================================
# 5. 로그인 및 사용자 관리
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

# [세션 유지] 새로고침해도 다시 로그인 안 하도록 쿠키에 세션을 심어둠.
# 쿠키엔 무작위 토큰(세션ID)만 넣고, 실제 아이디/권한/이름은 서버 메모리(이 dict)에만
# 보관함 -> 쿠키값이 새더라도 그 자체에서 로그인정보가 드러나지 않고, 로그아웃하면
# 즉시 무효화 가능함 (반대로 서버가 재시작되면 이 dict가 비워져서 전원 재로그인됨).
SESSION_MAX_AGE_DAYS = 7

@st.cache_resource
def _session_store():
    return {}

def make_session_token(username, role, name):
    token = secrets.token_urlsafe(32)
    _session_store()[token] = {
        "username": username, "role": role, "name": name,
        "issued": int(get_kst_now().timestamp())
    }
    return token

def verify_session_token(token):
    info = _session_store().get(token)
    if not info:
        return None
    if int(get_kst_now().timestamp()) - info["issued"] > SESSION_MAX_AGE_DAYS * 86400:
        del _session_store()[token]
        return None
    return info

def invalidate_session_token(token):
    _session_store().pop(token, None)

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
        clear_cache_after_save("access_logs")
    except: pass

# ==========================================
# 6. 엑셀 파싱 (핵심: 5001~5300 필터 + 노선 기억)
# ==========================================
def parse_roster_excel(file):
    df_raw = pd.read_excel(file, header=None)
    
    date_rows = []
    for idx, row in df_raw.iterrows():
        val = str(row[0])
        if ("202" in val or "년" in val):
            try:
                if pd.notnull(df_raw.iloc[idx, 3]) and pd.notnull(df_raw.iloc[idx, 5]):
                    date_rows.append(idx)
            except: pass
            
    extracted_data = []
    
    for i in range(len(date_rows)):
        start_row = date_rows[i]
        if i + 1 < len(date_rows): end_row = date_rows[i+1]
        else: end_row = len(df_raw)
            
        try:
            year = int(str(df_raw.iloc[start_row, 0]).replace("년","").strip())
            month = int(str(df_raw.iloc[start_row, 3]).replace("월","").strip())
            day = int(str(df_raw.iloc[start_row, 5]).replace("일","").strip())
            current_date = datetime(year, month, day).strftime("%Y-%m-%d")
        except: continue 

        cols_map = [
            {'route':1, 'seq':2, 'car':3, 'am_fix':4, 'am_sub':5, 'pm_fix':6, 'pm_sub':7},
            {'route':9, 'seq':10, 'car':11, 'am_fix':12, 'am_sub':13, 'pm_fix':14, 'pm_sub':15}
        ]
        
        for side in cols_map:
            # [기억 변수] 병합된 정보를 채우기 위함
            last_route = None
            last_car = None 
            
            for curr_idx in range(start_row + 3, end_row):
                try:
                    # 1. 노선 (Fill-down: 비어있으면 윗줄 값 사용)
                    raw_route = df_raw.iloc[curr_idx, side['route']]
                    if pd.notnull(raw_route) and str(raw_route).strip() != "":
                        current_route = str(raw_route).strip()
                        last_route = current_route # 갱신
                    else:
                        current_route = last_route if last_route else ""

                    # 2. 순번
                    raw_seq = df_raw.iloc[curr_idx, side['seq']]
                    current_seq = str(raw_seq).strip() if pd.notnull(raw_seq) else ""
                    
                    # 3. 차량번호 (핵심 필터링: 5001 ~ 5300 아니면 무시)
                    raw_car = df_raw.iloc[curr_idx, side['car']]
                    current_car = ""
                    
                    if pd.notnull(raw_car):
                        raw_car_str = str(raw_car).strip()
                        digits = re.sub(r'[^0-9]', '', raw_car_str)
                        
                        # [절대 규칙] 숫자가 5001~5300 사이여야만 차량으로 인정
                        if digits and (5001 <= int(digits) <= 5300):
                            current_car = str(int(digits))
                            last_car = current_car # 유효한 차량만 기억
                        else:
                            # 5001~5300이 아닌 숫자(예: 10대, 5명)는 아예 무시 -> 기억도 초기화
                            # 이렇게 하면 "합계" 줄이 "5024"로 채워지는 것을 방지
                            current_car = ""
                            last_car = None
                    
                    # [Fill-down] 현재 줄이 비어있고, 윗줄이 유효했으면 채운다.
                    if not current_car and last_car:
                        current_car = last_car
                    
                    # [최종 확인] 유효한 차량번호(5001~5300)가 없으면 이 줄은 데이터가 아님 (삭제)
                    if not current_car:
                        continue

                    # 4. 운전자 (필터 제거: 차량번호가 확실하므로 이름은 믿고 쓴다)
                    am_fix = clean_driver_name(df_raw.iloc[curr_idx, side['am_fix']])
                    am_sub = clean_driver_name(df_raw.iloc[curr_idx, side['am_sub']])
                    am_final = am_sub if am_sub else am_fix
                    
                    pm_fix = clean_driver_name(df_raw.iloc[curr_idx, side['pm_fix']])
                    pm_sub = clean_driver_name(df_raw.iloc[curr_idx, side['pm_sub']])
                    pm_final = pm_sub if pm_sub else pm_fix
                    
                    # 이름 뒤 숫자만 제거 (혹시 모르니)
                    if am_final: am_final = re.sub(r'[0-9]+', '', am_final).strip()
                    if pm_final: pm_final = re.sub(r'[0-9]+', '', pm_final).strip()

                    # 저장
                    extracted_data.append({
                        'date': current_date, 'name': am_final, 'shift': '오전', 
                        'route': current_route, 'seq': current_seq, 'car': current_car, 
                        'is_sub': bool(am_sub), 'orig_fix': am_fix
                    })
                    
                    extracted_data.append({
                        'date': current_date, 'name': pm_final, 'shift': '오후', 
                        'route': current_route, 'seq': current_seq, 'car': current_car, 
                        'is_sub': bool(pm_sub), 'orig_fix': pm_fix
                    })
                except Exception:
                    continue

    return pd.DataFrame(extracted_data)

# ... (나머지 함수 기존 유지) ...
def get_admin_memo():
    sh = get_db_connection()
    try:
        ws = sh.worksheet("admin_memo")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="admin_memo", rows=10, cols=2)
        try:
            ws.update(values=[[""]], range_name="A1", value_input_option='USER_ENTERED')
        except:
            ws.update("A1", [[""]], value_input_option='USER_ENTERED')
    
    val = ws.acell('A1').value
    return val if val else ""

def save_admin_memo(text):
    sh = get_db_connection()
    try:
        ws = sh.worksheet("admin_memo")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="admin_memo", rows=10, cols=2)
    
    try:
        ws.update(values=[[text]], range_name="A1", value_input_option='USER_ENTERED')
    except:
        ws.update("A1", [[text]], value_input_option='USER_ENTERED')

# ... (기존 코드들) ...

# [추가] 관리자 비밀번호 검증 함수
def verify_admin_password(input_pw):
    # 입력된 비밀번호를 해시화
    input_hash = make_hash(input_pw)
    
    # users 시트에서 관리자(admin) 권한을 가진 사람의 비밀번호와 일치하는지 확인
    df_users = load_data("users")
    if df_users.empty: return False
    
    # role이 'admin'인 행들만 필터링
    admins = df_users[df_users['role'] == 'admin']
    
    # 관리자 중 비밀번호가 일치하는 사람이 한 명이라도 있으면 통과
    if input_hash in admins['password'].values:
        return True
    return False

# [추가] 스케줄 삭제 함수 (조건 매칭)
def delete_schedule_event(date_str, name, type_str):
    sh = get_db_connection()
    ws = sh.worksheet("schedules")
    
    # 모든 데이터 가져오기
    # (행 번호를 알아야 삭제 가능하므로 cell 객체 검색보다 전체 로드 후 매칭이 안전할 수 있음)
    # 하지만 데이터가 많아지면 느려지므로, 여기서는 텍스트 검색을 활용
    
    try:
        # 날짜로 먼저 필터링 (날짜열: C열, 인덱스 3)
        cell_list = ws.findall(date_str)
        
        target_row = None
        for cell in cell_list:
            # 해당 행의 이름(B열)과 타입(D열) 확인
            row_val = ws.row_values(cell.row)
            # row_val[1] = Name, row_val[2] = Date, row_val[3] = Type
            if len(row_val) > 3:
                if row_val[1] == name and row_val[3] == type_str:
                    target_row = cell.row
                    break
        
        if target_row:
            ws.delete_rows(target_row)
            clear_cache_after_save("schedules")
            return True
        else:
            return False
            
    except Exception as e:
        st.error(f"삭제 중 오류 발생: {e}")
        return False
