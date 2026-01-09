import streamlit as st
import pandas as pd
import utils

def _get_history_dict():
    """조(Group) 히스토리를 딕셔너리 형태로 로드"""
    gh = utils.load_data("group_history")
    h_dict = {}
    if not gh.empty:
        for _, r in gh.iterrows():
            if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
            h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
        for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
    return h_dict

def _render_search_logic(is_admin=False):
    # 1. 데이터 로드
    df = utils.load_data("schedules")
    
    if df.empty:
        st.info("데이터가 없습니다.")
        return

    # 2. 검색 필터
    search_term = st.text_input("🔍 이름 또는 비고 검색", placeholder="이름을 입력하세요")
    
    if search_term:
        # 이름이나 비고에 검색어가 포함된 경우 필터링
        df = df[
            df['name'].astype(str).str.contains(search_term) | 
            df['note'].astype(str).str.contains(search_term)
        ]

    # 3. 데이터 가공 (원래 근무 계산)
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
        
        # 4. 컬럼 선택 및 순서 재배치 (요청사항 반영)
        # 날짜, 이름, 구분, 원래 근무, 비고 순서
        display_cols = ['date', 'name', 'type', 'orig_shift', 'note']
        
        df_display = df[display_cols].copy()
        
        # 5. 컬럼명 한글화
        df_display.columns = ['날짜', '이름', '구분', '원래 근무', '비고']
        
        # 6. 날짜 내림차순 정렬
        df_display = df_display.sort_values(by='날짜', ascending=False)

        # 7. 테이블 출력
        st.dataframe(
            df_display, 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.info("검색 결과가 없습니다.")

# ==========================================
# 관리자용 조회 탭
# ==========================================
def render_view_manage_tab():
    st.subheader("📊 데이터 조회 (관리자)")
    _render_search_logic(is_admin=True)

# ==========================================
# 일반 직원용 조회 탭
# ==========================================
def render_public_search_tab():
    st.subheader("📊 데이터 조회")
    _render_search_logic(is_admin=False)
