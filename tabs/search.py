import streamlit as st
import pandas as pd
import io
import calendar
import concurrent.futures
import utils

# ... (헬퍼 함수들은 기존과 동일) ...
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

def _get_history_dict():
    gh = utils.load_data("group_history")
    h_dict = {}
    if not gh.empty:
        for _, r in gh.iterrows():
            # [수정] utils.get_group_from_dict과 짝을 맞춰 정규화된 이름을 키로 씀
            key = utils.norm_name(r['driver_name'])
            if key not in h_dict: h_dict[key] = []
            h_dict[key].append((r['start_date'], r['group_name']))
        for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
    return h_dict

def _render_detail_search(is_admin=False):
    with st.container(key="inlinerow_detailsearch"):
        c_input, c_btn = st.columns([1, 1])
        with c_input:
            search_term = st.text_input("🔍 이름 또는 비고 검색", placeholder="이름/비고", key="search_term_input", label_visibility="collapsed")
        with c_btn:
            # [최적화] 버튼을 누르기 전엔 schedules를 아예 안 불러옴
            query_clicked = st.button("🔍 조회", key="btn_query_detail", type="primary")
    if query_clicked:
        st.session_state['search_detail_queried'] = True
    if not st.session_state.get('search_detail_queried'):
        st.info("조회 버튼을 눌러주세요.")
        return

    df = utils.load_data("schedules")
    if df.empty: st.info("데이터가 없습니다."); return
    if search_term: df = df[df['name'].astype(str).str.contains(search_term) | df['note'].astype(str).str.contains(search_term)]
    if not df.empty:
        h_dict = _get_history_dict()
        orig_shifts = []
        # [최적화] iterrows() 대신 zip으로 순회
        for d_str, name in zip(df['date'], df['name']):
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
    now = utils.get_kst_now()
    with st.container(key="inlinerow_yearly"):
        # [참고] 컬럼 실제 폭은 utils.inject_custom_css()의 inlinerow_yearly CSS가 고정폭으로
        # 강제하므로, 여기 비율은 그 CSS가 안 먹는 극단적 상황에서의 대비용일 뿐 큰 의미 없음
        c_yr_txt, c_yr, c_btn = st.columns([0.4, 0.7, 0.7])
        with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
        with c_yr:
            year_range = range(2023, now.year + 3)
            try: y_idx = list(year_range).index(st.session_state.search_stat_year)
            except: y_idx = 0
            sel_year = st.selectbox("년도", year_range, index=y_idx, key='sb_search_year', label_visibility="collapsed")
            if sel_year != st.session_state.search_stat_year: st.session_state.search_stat_year = sel_year; st.rerun(scope="fragment")
        with c_btn:
            # [최적화] 버튼을 누르기 전엔 work_history를 아예 안 불러옴
            query_clicked = st.button("📊 조회", key="btn_query_yearly", type="primary")
    st.info("💡 **25일 이상** 근무한 달이 **3개월 연속**되면 빨간색으로 표시됩니다.")
    if query_clicked:
        st.session_state['search_yearly_queried'] = True
    st.divider()
    if not st.session_state.get('search_yearly_queried'):
        st.info("조회 버튼을 눌러주세요.")
        return

    year = st.session_state.search_stat_year
    # [최적화] 무관한 시트 2개를 동시에 요청 + work_history는 선택된 연도 시트만 읽음
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as _ex:
        _f_drivers = _ex.submit(utils.load_data, "drivers")
        _f_work = _ex.submit(utils.load_work_history_for_year, year)
        try:
            df_drivers = _f_drivers.result()
            df_work = _f_work.result()
        except Exception as e:
            st.error(f"❌ 데이터 로딩 중 오류가 발생했습니다: {e}")
            st.stop()
    if df_drivers.empty: st.warning("등록된 승무원이 없습니다."); return
    result_data = []
    sorted_drivers = df_drivers.sort_values(by='name')['name'].tolist()
    if not df_work.empty:
        df_work = df_work.copy()
        df_work['dt'] = pd.to_datetime(df_work['date'], errors='coerce')
        df_year = df_work[(df_work['dt'].dt.year == year) & (df_work['shift'].isin(['오전', '오후']))]
    else: df_year = pd.DataFrame()

    # [최적화] 승무원 358명 x 12개월을 매번 필터링하던 걸 -> groupby로 한 번에 집계 (13,000+회 필터 호출 제거)
    if not df_year.empty:
        df_year = df_year.copy()
        df_year['month'] = df_year['dt'].dt.month
        pivot = df_year.groupby(['name', 'month']).size().unstack(fill_value=0).reindex(columns=range(1, 13), fill_value=0)
    else:
        pivot = pd.DataFrame(columns=range(1, 13))

    for name in sorted_drivers:
        row_data = {"이름": name}
        counts = pivot.loc[name] if name in pivot.index else None
        total_year = 0
        for m in range(1, 13):
            cnt = int(counts[m]) if counts is not None else 0
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
# 4. [탭3] 월간 차량별 근무자 현황 (최종 로직)
# ==========================================
def _highlight_gamcha_cells(val):
    if val == "감차": return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;'
    return ''

def _render_vehicle_stats_logic():
    _init_search_session_state()
    with st.container(key="inlinerow_vehicle"):
        # [참고] 컬럼 실제 폭은 utils.inject_custom_css()의 inlinerow_vehicle CSS가 고정폭으로
        # 강제함(월 이동 210px + 버튼). 더 이상 남는 공간을 채울 빈 컬럼이 필요 없음.
        c_nav, c_btn = st.columns([1, 0.45])
        with c_nav:
            utils.render_month_nav("veh_month", "veh_year", "veh_month")
        with c_btn:
            # [최적화] 버튼을 누르기 전엔 work_history를 아예 안 불러옴
            query_clicked = st.button("🚌 조회", key="btn_query_vehicle", type="primary")
    if query_clicked:
        st.session_state['search_vehicle_queried'] = True
    st.divider()
    if not st.session_state.get('search_vehicle_queried'):
        st.info("조회 버튼을 눌러주세요.")
        return

    year = st.session_state.veh_year; month = st.session_state.veh_month; filter_ym = f"{year}-{month:02d}"
    reduction_rules = utils.get_reduction_rules()
    # [최적화] work_history 전체 대신 선택된 연도 시트만 읽음
    df_work = utils.load_work_history_for_year(year)

    if df_work.empty: st.info("근무 데이터가 없습니다."); return
    df_month = df_work[df_work['date'].astype(str).str.startswith(filter_ym)]
    if df_month.empty: st.info(f"{year}년 {month}월 데이터가 없습니다."); return

    valid_cars = df_month[df_month['car'].astype(str).str.strip() != ""]['car'].unique()
    def try_int(x):
        try: return int(x)
        except: return 999999
    sorted_cars = sorted(valid_cars, key=try_int)
    
    # [최적화] iterrows() 대신 zip으로 순회 (한 달치 근무기록 규모라도 Series 생성 비용을 피함)
    schedule_map = {}
    route_col = df_month['route'] if 'route' in df_month.columns else pd.Series([''] * len(df_month), index=df_month.index)
    seq_col = df_month['seq'] if 'seq' in df_month.columns else pd.Series([''] * len(df_month), index=df_month.index)
    for date_val, car_val, shift_val, name_val, route_val, seq_val in zip(
        df_month['date'], df_month['car'], df_month['shift'], df_month['name'], route_col, seq_col
    ):
        try:
            d = int(pd.to_datetime(date_val).day)
            c = str(car_val).strip()
            s = str(shift_val).strip()
            n = str(name_val).strip()
            r_num = str(route_val).strip()
            r_seq = str(seq_val).strip()
            key = (d, c, s)
            # 이름이 있는 데이터를 우선시 (중복시 빈칸 데이터는 무시)
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
                # [규칙 1] 이 차량이 감차 대상이면? -> 무조건 "감차" (이름 덮어씌움)
                if utils.is_reduction_target(date_str, data_am['route'], data_am['seq'], reduction_rules):
                    val_am = "감차"
                # [규칙 2] 감차 아닌데 이름 있으면? -> 이름
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

_SEARCH_SUBMENU = ["상세 이력 조회", "연간 근무 집계", "월간 차량별 현황"]

@st.fragment
def render_view_manage_tab():
    section = utils.render_submenu(_SEARCH_SUBMENU, "submenu_search_admin")
    if section == "연간 근무 집계": _render_yearly_stats_logic()
    elif section == "월간 차량별 현황": _render_vehicle_stats_logic()
    else: _render_detail_search(is_admin=True)

@st.fragment
def render_public_search_tab():
    section = utils.render_submenu(_SEARCH_SUBMENU, "submenu_search_public")
    if section == "연간 근무 집계": _render_yearly_stats_logic()
    elif section == "월간 차량별 현황": _render_vehicle_stats_logic()
    else: _render_detail_search(is_admin=False)
