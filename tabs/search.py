import streamlit as st
import pandas as pd
import io
import utils
import calendar  # 추가됨
from datetime import datetime

# ==========================================
# 1. 내부 헬퍼 함수 (기존 유지)
# ==========================================
def _init_search_session_state():
    now = utils.get_kst_now()
    if 'search_stat_year' not in st.session_state:
        st.session_state.search_stat_year = now.year
    # 차량 조회용 세션 상태 추가
    if 'car_view_year' not in st.session_state:
        st.session_state.car_view_year = now.year
    if 'car_view_month' not in st.session_state:
        st.session_state.car_view_month = now.month

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

# ... [기존 _render_detail_search, _highlight_consecutive_months, _render_monthly_stats_logic 함수는 그대로 유지] ...

# ==========================================
# 4. [탭3] 월간 차량별 현황 (신규 추가)
# ==========================================
def _render_monthly_car_matrix():
    _init_search_session_state()
    
    # --- 날짜 선택 컨트롤 ---
    c1, c2, c_empty = st.columns([0.4, 0.4, 2])
    with c1:
        sel_year = st.selectbox("연도", range(2024, 2028), index=datetime.now().year - 2024, key="car_yr")
    with c2:
        sel_month = st.selectbox("월", range(1, 13), index=datetime.now().month - 1, key="car_mo")
    
    st.info("💡 가로축은 **날짜**, 세로축은 **차량번호**입니다. (표시: 오전근무자 / 오후근무자)")

    # 데이터 로드
    df_work = utils.load_data("work_history")
    if df_work.empty:
        st.warning("배차 데이터(work_history)가 없습니다.")
        return

    # 해당 월 데이터 필터링
    df_work['dt'] = pd.to_datetime(df_work['date'], errors='coerce')
    df_target = df_work[(df_work['dt'].dt.year == sel_year) & (df_work['dt'].dt.month == sel_month)].copy()

    if df_target.empty:
        st.info(f"{sel_year}년 {sel_month}월에 해당하는 데이터가 없습니다.")
        return

    # 데이터 가공: 오전/오후 합치기
    # 1. 차량번호 숫자로 변환 (정렬용)
    df_target['car'] = pd.to_numeric(df_target['car'], errors='coerce')
    df_target = df_target.dropna(subset=['car'])
    
    # 2. 피벗 생성을 위한 결합 함수
    def get_combined_drivers(group):
        am = group[group['shift'] == '오전']['name'].iloc[0] if not group[group['shift'] == '오전'].empty else "-"
        pm = group[group['shift'] == '오후']['name'].iloc[0] if not group[group['shift'] == '오후'].empty else "-"
        return f"{am} / {pm}"

    # 3. 피벗 테이블 생성
    # index: 차량, columns: 날짜(일만 표시), values: 결합된 이름
    df_target['day'] = df_target['dt'].dt.day
    matrix = df_target.groupby(['car', 'day']).apply(get_combined_drivers).unstack(fill_value="-")

    # 해당 월의 모든 날짜(1일~말일) 컬럼 보장
    last_day = calendar.monthrange(sel_year, sel_month)[1]
    all_days = list(range(1, last_day + 1))
    for d in all_days:
        if d not in matrix.columns:
            matrix[d] = "-"
    
    # 컬럼 순서 정렬 및 차량번호 정렬
    matrix = matrix[all_days].sort_index()
    
    # 컬럼명을 "1일", "2일"... 형태로 변경
    matrix.columns = [f"{d}일" for d in matrix.columns]
    matrix.index.name = "차량번호"

    # 테이블 출력
    st.dataframe(matrix, use_container_width=True, height=600)

    # 엑셀 다운로드
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        matrix.to_excel(writer, sheet_name='차량별현황')
    processed_data = output.getvalue()
    
    st.download_button(
        label="📥 차량별 현황 엑셀 다운로드",
        data=processed_data,
        file_name=f"{sel_year}년{sel_month}월_차량별_배차현황.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ==========================================
# 메인 렌더링 함수 (수정됨)
# ==========================================
def render_view_manage_tab():
    st.subheader("📊 데이터 조회 (관리자)")
    t1, t2, t3 = st.tabs(["🔍 상세 이력 조회", "📅 연간 근무 집계", "🚌 월간 차량별 현황"])
    with t1: _render_detail_search(is_admin=True)
    with t2: _render_monthly_stats_logic()
    with t3: _render_monthly_car_matrix()

def render_public_search_tab():
    st.subheader("📊 데이터 조회")
    t1, t2, t3 = st.tabs(["🔍 상세 이력 조회", "📅 연간 근무 집계", "🚌 월간 차량별 현황"])
    with t1: _render_detail_search(is_admin=False)
    with t2: _render_monthly_stats_logic()
    with t3: _render_monthly_car_matrix()
