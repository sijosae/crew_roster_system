import streamlit as st
import pandas as pd
import io
import calendar
import utils

# ... (기존 헬퍼 함수들은 그대로 유지) ...
def _init_search_session_state():
    now = utils.get_kst_now()
    if 'search_stat_year' not in st.session_state: st.session_state.search_stat_year = now.year
    if 'search_stat_month' not in st.session_state: st.session_state.search_stat_month = now.month
    if 'veh_year' not in st.session_state: st.session_state.veh_year = now.year
    if 'veh_month' not in st.session_state: st.session_state.veh_month = now.month

def _prev_month_search():
    if st.session_state.search_stat_month == 1: st.session_state.search_stat_year -= 1; st.session_state.search_stat_month = 12
    else: st.session_state.search_stat_month -= 1
    st.session_state.sb_search_year = st.session_state.search_stat_year

def _next_month_search():
    if st.session_state.search_stat_month == 12: st.session_state.search_stat_year += 1; st.session_state.search_stat_month = 1
    else: st.session_state.search_stat_month += 1
    st.session_state.sb_search_year = st.session_state.search_stat_year

def _prev_month_veh():
    if st.session_state.veh_month == 1: st.session_state.veh_year -= 1; st.session_state.veh_month = 12
    else: st.session_state.veh_month -= 1

def _next_month_veh():
    if st.session_state.veh_month == 12: st.session_state.veh_year += 1; st.session_state.veh_month = 1
    else: st.session_state.veh_month += 1

def _get_history_dict():
    gh = utils.load_data("group_history")
    h_dict = {}
    if not gh.empty:
        for _, r in gh.iterrows():
            if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
            h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
        for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
    return h_dict

def _render_detail_search(is_admin=False):
    df = utils.load_data("schedules")
    if df.empty: st.info("데이터가 없습니다."); return
    search_term = st.text_input("🔍 이름 또는 비고 검색", placeholder="이름을 입력하세요", key="search_term_input")
    if search_term:
        df = df[df['name'].astype(str).str.contains(search_term) | df['note'].astype(str).str.contains(search_term)]
    if not df.empty:
        h_dict = _get_history_dict()
        orig_shifts = []
        for _, row in df.iterrows():
            d_str = row['date']; name = row['name']
            grp = utils.get_group_from_dict(h_dict, name, d_str)
            auto = utils.calculate_auto_shift(grp, d_str)
            if grp and auto: orig_shifts.append(f"{auto} ({grp})")
            else: orig_shifts.append("-")
        df['orig_shift'] = orig_shifts
        display_cols = ['date', 'name', 'type', 'orig_shift', 'note']
        df_display = df[display_cols].copy()
        df_display.columns = ['날짜', '이름', '구분', '원래 근무', '비고']
        df_display = df_display.sort_values(by='날짜', ascending=False)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_display.to_excel(writer, index=False, sheet_name='조회결과')
        st.download_button(label="📥 엑셀로 다운로드", data=output.getvalue(), file_name="배차조회결과.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="btn_down_detail")
    else: st.info("검색 결과가 없습니다.")

def _highlight_consecutive_months(data):
    bg_styles = pd.DataFrame('', index=data.index, columns=data.columns)
    month_cols = [f"{i}월" for i in range(1, 13)]
    for idx, row in data.iterrows():
        counts = [row[c] for c in month_cols]
        mask = [False] * 12
        for i in range(10):
            if counts[i] >= 25 and counts[i+1] >= 25 and counts[i+2] >= 25: mask[i]=True; mask[i+1]=True; mask[i+2]=True
        for col_idx, is_highlight in enumerate(mask):
            if is_highlight: bg_styles.at[idx, month_cols[col_idx]] = 'background-color: #ffcccc; color: #990000; font-weight: bold;'
    return bg_styles

def _render_yearly_stats_logic():
    _init_search_session_state()
    c_yr_txt, c_yr, c_empty = st.columns([0.2, 0.4, 2])
    now = utils.get_kst_now()
    with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        year_range = range(2023, now.year + 3)
        try: y_idx = list(year_range).index(st.session_state.search_stat_year)
        except: y_idx = 0
        sel_year = st.selectbox("년도", year_range, index=y_idx, key='sb_search_year', label_visibility="collapsed")
        if sel_year != st.session_state.search_stat_year: st.session_state.search_stat_year = sel_year; st.rerun()
    st.info("💡 **25일 이상** 근무한 달이 **3개월 연속**되면 빨간색으로 표시됩니다.")
    st.divider()
    year = st.session_state.search_stat_year
    df_drivers = utils.load_data("drivers")
    if df_drivers.empty: st.warning("등록된 승무원이 없습니다."); return
    df_work = utils.load_data("work_history")
    result_data = []
    sorted_drivers = df_drivers.sort_values(by='name')['name'].tolist()
    if not df_work.empty:
        df_work['dt'] = pd.to_datetime(df_work['date'], errors='coerce')
        df_year = df_work[df_work['dt'].dt.year == year]
    else: df_year = pd.DataFrame()
    for name in sorted_drivers:
        row_data = {"이름": name}; total_year = 0
        my_data = df_year[df_year['name'] == name] if not df_year.empty else pd.DataFrame()
        for m in range(1, 13):
            if not my_data.empty: cnt = len(my_data[(my_data['dt'].dt.month == m) & (my_data['shift'].isin(['오전', '오후']))])
            else: cnt = 0
            row_data[f"{m}월"] = cnt; total_year += cnt
        row_data["연간 합계"] = total_year; result_data.append(row_data)
    if result_data:
        df_res = pd.DataFrame(result_data)
        cols = ["이름"] + [f"{i}월" for i in range(1, 13)] + ["연간 합계"]
        st.dataframe(df_res[cols].style.apply(_highlight_consecutive_months, axis=None), use_container_width=True, hide_index=True, column_config={"이름": st.column_config.TextColumn("이름", width="medium"), "연간 합계": st.column_config.NumberColumn("합계", format="%d일")}, height=600)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_res[cols].to_excel(writer, index=False, sheet_name=f'{year}년_근무집계')
        st.download_button(label="📥 집계표 엑셀 다운로드", data=output.getvalue(), file_name=f"{year}년_승무원_연간근무현황.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="btn_down_stats_yearly")
    else: st.info("데이터가 없습니다.")

# ==========================================
# 4. [탭3] 월간 차량별 근무자 현황 (우선순위 최종 확정)
# ==========================================
def _highlight_gamcha_cells(val):
    if val == "감차": return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;'
    return ''

def _render_vehicle_stats_logic():
    _init_search_session_state()
    c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([0.4, 0.8, 0.3, 0.7, 0.4, 0.4])
    now = utils.get_kst_now()
    with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        year_range = range(2023, now.year + 3)
        try: y_idx = list(year_range).index(st.session_state.veh_year)
        except: y_idx = 0
        st.selectbox("년도", year_range, index=y_idx, key='veh_year', label_visibility="collapsed")
    with c_mo_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c_mo: 
        month_range = range(1, 13)
        st.selectbox("월", month_range, index=st.session_state.veh_month - 1, key='veh_month', label_visibility="collapsed")
    with c_prev: st.button("◀", key="v_prev_btn", on_click=_prev_month_veh)
    with c_next: st.button("▶", key="v_next_btn", on_click=_next_month_veh)
    st.divider()

    year = st.session_state.veh_year; month = st.session_state.veh_month; filter_ym = f"{year}-{month:02d}"
    reduction_rules = utils.get_reduction_rules()
    df_work = utils.load_data("work_history")
    
    if df_work.empty: st.info("근무 데이터가 없습니다."); return
    df_month = df_work[df_work['date'].astype(str).str.startswith(filter_ym)]
    if df_month.empty: st.info(f"{year}년 {month}월 데이터가 없습니다."); return

    valid_cars = df_month[df_month['car'].astype(str).str.strip() != ""]['car'].unique()
    def try_int(x):
        try: return int(x)
        except: return 999999
    sorted_cars = sorted(valid_cars, key=try_int)
    
    # DB 데이터 매핑 (이름이 있는 데이터를 최우선으로 저장)
    schedule_map = {}
    for _, row in df_month.iterrows():
        try:
            d = int(pd.to_datetime(row['date']).day)
            c = str(row['car']).strip()
            s = str(row['shift']).strip() 
            n = str(row['name']).strip()
            r_num = str(row.get('route', '')).strip()
            r_seq = str(row.get('seq', '')).strip()
            
            key = (d, c, s)
            # 만약 이미 데이터가 있는데, 새 데이터는 이름이 없다면(빈칸) -> 덮어쓰지 않음
            if key in schedule_map and schedule_map[key]['name'] != "" and n == "": continue
            schedule_map[key] = {'name': n, 'route': r_num, 'seq': r_seq}
        except: continue
            
    _, last_day = calendar.monthrange(year, month)
    table_data = []
    
    for car in sorted_cars:
        row_am = {'차량번호': car, '구분': '오전'}; row_pm = {'차량번호': car, '구분': '오후'}
        for d in range(1, last_day + 1):
            date_str = f"{year}-{month:02d}-{d:02d}"
            
            # --- [오전] ---
            data_am = schedule_map.get((d, car, '오전'))
            val_am = ""
            if data_am:
                # [규칙 1] 감차 대상이면 무조건 "감차" (이름 덮어씀) - 5036호 해결
                if utils.is_reduction_target(date_str, data_am['route'], data_am['seq'], reduction_rules):
                    val_am = "감차"
                # [규칙 2] 감차가 아니고 이름이 있으면 이름 표시 - 5024호 해결
                elif data_am['name']:
                    val_am = data_am['name']
                else: val_am = ""
            
            # --- [오후] ---
            data_pm = schedule_map.get((d, car, '오후'))
            val_pm = ""
            if data_pm:
                if utils.is_reduction_target(date_str, data_pm['route'], data_pm['seq'], reduction_rules):
                    val_pm = "감차"
                elif data_pm['name']:
                    val_pm = data_pm['name']
                else: val_pm = ""
            
            row_am[f"{d}일"] = val_am; row_pm[f"{d}일"] = val_pm
        table_data.append(row_am); table_data.append(row_pm)
        
    if table_data:
        df_res = pd.DataFrame(table_data)
        cols = ['차량번호', '구분'] + [f"{d}일" for d in range(1, last_day + 1)]
        st.dataframe(df_res[cols].style.map(_highlight_gamcha_cells), use_container_width=True, hide_index=True, column_config={"차량번호": st.column_config.TextColumn("차량", width="small"), "구분": st.column_config.TextColumn("근무", width="small")}, height=600)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_res[cols].to_excel(writer, index=False, sheet_name=f'{month}월_차량별현황')
        st.download_button(label="📥 차량별 현황 엑셀 다운로드", data=output.getvalue(), file_name=f"{year}년_{month}월_차량별근무현황.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="btn_down_vehicle_stats")
    else: st.info("표시할 데이터가 없습니다.")

def render_view_manage_tab():
    st.subheader("📊 데이터 조회 (관리자)")
    t1, t2, t3 = st.tabs(["🔍 상세 이력 조회", "📅 연간 근무 집계", "🚌 월간 차량별 현황"])
    with t1: _render_detail_search(is_admin=True)
    with t2: _render_yearly_stats_logic()
    with t3: _render_vehicle_stats_logic()

def render_public_search_tab():
    st.subheader("📊 데이터 조회")
    t1, t2, t3 = st.tabs(["🔍 상세 이력 조회", "📅 연간 근무 집계", "🚌 월간 차량별 현황"])
    with t1: _render_detail_search(is_admin=False)
    with t2: _render_yearly_stats_logic()
    with t3: _render_vehicle_stats_logic()
