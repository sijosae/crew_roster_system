import streamlit as st
import pandas as pd
import utils
from datetime import datetime

def render_driver_manage_tab():
    st.subheader("⚙️ 승무원 및 조 편성 관리")
    
    t1, t2 = st.tabs(["📋 승무원 목록/등록", "🚪 퇴사 처리"])
    
    # ----------------------------------------------------
    # 탭 1: 승무원 목록 및 신규 등록
    # ----------------------------------------------------
    with t1:
        # 신규 등록
        with st.expander("➕ 신규 승무원 등록"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1: new_name = st.text_input("이름")
            with c2: new_group = st.selectbox("소속 조", [f"{i}조" for i in range(1, 11)])
            with c3: new_date = st.date_input("배정일", value=datetime(2020,1,1))
            
            if st.button("승무원 등록"):
                if new_name:
                    utils.add_driver_with_group(new_name, new_group, str(new_date))
                    st.success(f"{new_name}님 등록 완료")
                    st.rerun()
                else:
                    st.warning("이름을 입력하세요.")

        st.divider()
        
        # 목록 조회
        df = utils.load_data("drivers")
        if not df.empty:
            # [핵심] 상태(status) 컬럼 재계산 로직
            # DB에 'active'라고 적혀있어도, 퇴사일이 지났으면 '퇴사'로 보여줌
            today_str = utils.get_kst_now().strftime("%Y-%m-%d")
            
            status_list = []
            for _, row in df.iterrows():
                r_date = str(row.get('resigned_date', '')).strip()
                if r_date and r_date <= today_str:
                    status_list.append("퇴사")
                else:
                    status_list.append("재직")
            
            df['status_calc'] = status_list
            
            # 화면 표시용 컬럼 정리
            display_df = df[['name', 'group', 'resigned_date', 'status_calc']].copy()
            display_df.columns = ['이름', '현재 조', '퇴사일', '상태']
            
            # 재직자 위주로 정렬 (퇴사자는 아래로)
            display_df = display_df.sort_values(by=['상태', '이름'], ascending=[False, True])
            
            st.dataframe(
                display_df, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "상태": st.column_config.TextColumn(
                        "상태", 
                        help="퇴사일이 지나면 자동으로 퇴사로 표시됩니다.",
                        width="small"
                    )
                }
            )
        else:
            st.info("등록된 승무원이 없습니다.")

    # ----------------------------------------------------
    # 탭 2: 퇴사 처리
    # ----------------------------------------------------
    with t2:
        st.write("승무원을 퇴사 처리하거나, 데이터를 삭제합니다.")
        
        df = utils.load_data("drivers")
        if df.empty:
            st.warning("데이터 없음")
            return
            
        target_driver = st.selectbox("대상 승무원 선택", df['name'].unique())
        
        c_act1, c_act2 = st.columns(2)
        
        # 1. 퇴사 처리 (날짜 입력)
        with c_act1:
            st.markdown("##### 👋 퇴사 처리")
            r_date = st.date_input("퇴사 일자", value=datetime.now())
            if st.button("퇴사 적용", type="primary"):
                utils.set_driver_resignation(target_driver, str(r_date))
                st.success(f"{target_driver}님 퇴사 처리 완료 ({r_date})")
                st.rerun()
                
        # 2. 데이터 삭제 (주의)
        with c_act2:
            st.markdown("##### 🗑️ 데이터 완전 삭제")
            st.caption("주의: 근무 기록까지 모두 삭제됩니다.")
            if st.button("승무원 삭제 (복구 불가)"):
                utils.delete_driver(target_driver)
                st.error(f"{target_driver}님 데이터 삭제 완료")
                st.rerun()
