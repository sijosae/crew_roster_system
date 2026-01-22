import streamlit as st
import pandas as pd
import io
import utils

# ==========================================
# 1. 내부 헬퍼 함수
# ==========================================
def _init_search_session_state():
    now = utils.get_kst_now()
    if 'search_stat_year' not in st.session_state:
        st.session_state.search_stat_year = now.year

def _get_history_dict():
    """조(Group) 히스토리 로드"""
    gh = utils.load_data("group_history")
    h_dict = {}
    if not gh.empty:
        for _, r in gh.iterrows():
            if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
            h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
        for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
    return h_dict

# ==========================================
# 2. [탭1] 상세 이력 조회 (기존 유지)
# ==========================================
def _render_detail_search(is_admin=False):
    # 데이터 로드
    df = utils.load_data("schedules")
    
    if df.empty:
        st.info("데이터가 없습니다.")
        return

    # 검색 필터
    search_term = st.text_input("🔍 이름 또는 비고 검색", placeholder="이름을 입력하세요", key="search_term_input")
    
    if search_term:
        df = df[
            df['name'].astype(str).str.contains(search_term) | 
            df['note'].astype(str).str.contains(search_term)
        ]

    # 데이터 가공
    if not df.empty:
        h_dict = _get_history_dict()
        orig_shifts = []
        
        for _, row in df.iterrows():
            d_str = row['date']
            name = row['name']
            grp = utils.get_group_from_dict(h_dict, name, d_str)
            auto = utils.calculate_auto_shift(grp, d_str)
            if grp and auto:
                orig_shifts.append(f"{auto} ({grp})")
            else:
                orig_shifts.append("-")
        
        df['orig_shift'] = orig_shifts
        
        # 컬럼 재배치
        display_cols = ['date', 'name', 'type', 'orig_shift', 'note']
        df_display = df[display_cols].copy()
        df_display.columns = ['날짜', '이름', '구분', '원래 근무', '비고']
        df_display = df_display.sort_values(by='날짜', ascending=False)

        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_display.to_excel(writer, index=False, sheet_name='조회결과')
        processed_data = output.getvalue()
        
        st.download_button(
            label="📥 엑셀로 다운로드",
            data=processed_data,
            file_name="배차조회결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_down_detail"
        )
    else:
        st.info("검색 결과가 없습니다.")

# ==========================================
# 3. [탭2] 연간 근무 집계 (신규 기능)
# ==========================================
def _highlight_consecutive_months(data):
    """
    스타일링 함수: 
    한 행(승무원)에서 25일 이상 근무한 달이 3회 이상 연속될 경우,
    해당하는 모든 달의 배경색을 빨간색으로 변경
    """
    bg_styles = pd.DataFrame('', index=data.index, columns=data.columns)
    month_cols = [f"{i}월" for i in range(1, 13)]
    
    for idx, row in data.iterrows():
        counts = [row[c] for c in month_cols]
        mask = [False] * 12
        
        for i in range(10):
            if counts[i] >= 25 and counts[i+1] >= 25 and counts[i+2] >= 25:
                mask[i] = True
                mask[i+1] = True
                mask[i+2] = True
        
        for col_idx, is_highlight in enumerate(mask):
            if is_highlight:
                col_name = month_cols[col_idx]
                bg_styles.at[idx, col_name] = 'background-color: #ffcccc; color: #990000; font-weight: bold;'
                
    return bg_styles

def _render_monthly_stats_logic():
    _init_search_session_state()
    
    # --- 날짜 컨트롤 (연도만 선택) ---
    c_yr_txt, c_yr, c_empty = st.columns([0.2, 0.4, 2])
    now = utils.get_kst_now()
    
    with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        year_range = range(2023, now.year + 3)
        try: y_idx = list(year_range).index(st.session_state.search_stat_year)
        except: y_idx = 0
        sel_year = st.selectbox("년도", year_range, index=y_idx, key='sb_search_year', label_visibility="collapsed")
        if sel_year != st.session_state.search_stat_year:
            st.session_state.search_stat_year = sel_year
            st.rerun()
    
    st.info("💡 **25일 이상** 근무한 달이 **3개월 연속**되면 빨간색으로 표시됩니다.")
    st.divider()
    
    # --- 데이터 집계 로직 ---
    year = st.session_state.search_stat_year
    
    df_drivers = utils.load_data("drivers")
    if df_drivers.empty:
        st.warning("등록된 승무원이 없습니다.")
        return
        
    df_work = utils.load_data("work_history")
    
    result_data = []
    sorted_drivers = df_drivers.sort_values(by='name')['name'].tolist()
    
    if not df_work.empty:
        df_work['dt'] = pd.to_datetime(df_work['date'], errors='coerce')
        df_year = df_work[df_work['dt'].dt.year == year]
    else:
        df_year = pd.DataFrame()

    for name in sorted_drivers:
        row_data = {"이름": name}
        total_year = 0
        
        my_data = df_year[df_year['name'] == name] if not df_year.empty else pd.DataFrame()
        
        for m in range(1, 13):
            if not my_data.empty:
                cnt = len(my_data[
                    (my_data['dt'].dt.month == m) & 
                    (my_data['shift'].isin(['오전', '오후']))
                ])
            else:
                cnt = 0
            
            row_data[f"{m}월"] = cnt
            total_year += cnt
            
        row_data["연간 합계"] = total_year
        result_data.append(row_data)
        
    if result_data:
        df_res = pd.DataFrame(result_data)
        cols = ["이름"] + [f"{i}월" for i in range(1, 13)] + ["연간 합계"]
        df_res = df_res[cols]
        
        # [수정] fixed=True 제거
        st.dataframe(
            df_res.style.apply(_highlight_consecutive_months, axis=None),
            use_container_width=True,
            hide_index=True,
            column_config={
                "이름": st.column_config.TextColumn("이름", width="medium"),
                "연간 합계": st.column_config.NumberColumn("합계", format="%d일")
            },
            height=600 
        )
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_res.to_excel(writer, index=False, sheet_name=f'{year}년_근무집계')
        processed_data = output.getvalue()
        
        st.download_button(
            label="📥 집계표 엑셀 다운로드",
            data=processed_data,
            file_name=f"{year}년_승무원_연간근무현황.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_down_stats_yearly"
        )
        
    else:
        st.info("데이터가 없습니다.")

# ==========================================
# 메인 렌더링 함수
# ==========================================
def render_view_manage_tab():
    st.subheader("📊 데이터 조회 (관리자)")
    t1, t2 = st.tabs(["🔍 상세 이력 조회", "📅 연간 근무 집계"])
    with t1: _render_detail_search(is_admin=True)
    with t2: _render_monthly_stats_logic()

def render_public_search_tab():
    st.subheader("📊 데이터 조회")
    t1, t2 = st.tabs(["🔍 상세 이력 조회", "📅 연간 근무 집계"])
    with t1: _render_detail_search(is_admin=False)
    with t2: _render_monthly_stats_logic()
