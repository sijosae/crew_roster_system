import streamlit as st
import pandas as pd
import utils

def render_driver_manage_tab():
    st.subheader("⚙️ 승무원 및 조(Group) 관리")
    
    # [복구] 4개 탭 구조 완벽 복원
    tab_bulk, tab_change, tab_resign, tab_users = st.tabs(["➕ 승무원 등록", "🔄 조 변경", "👋 퇴사 처리", "🔐 관리자 계정"])
    
    # ----------------------------------------------------
    # 1. 승무원 등록 (일괄 등록 기능 복구)
    # ----------------------------------------------------
    with tab_bulk:
        st.info("💡 엑셀에서 이름을 복사해서 붙여넣으면 한 번에 등록됩니다.")
        c1, c2 = st.columns([3, 1])
        with c1: bulk_names = st.text_area("승무원 성명 목록 (엔터로 구분)", height=150, placeholder="홍길동\n이철수\n박영희")
        with c2: 
            selected_group = st.selectbox("소속 조", [f"{i}조" for i in range(1, 11)] + ["기타"])
            st.markdown("<br>", unsafe_allow_html=True)
            start_date = st.date_input("조 배정 시작일", utils.get_kst_now().date())
            
            st.markdown('<div class="red-button">', unsafe_allow_html=True)
            if st.button("등록 실행", type="primary", use_container_width=True):
                if bulk_names:
                    names = [n.strip() for n in bulk_names.replace(',', '\n').split('\n') if n.strip()]
                    cnt = 0
                    for name in names:
                        if ',' in name or '\t' in name: parts = name.replace('\t', ',').split(','); name = parts[0].strip()
                        if utils.add_driver_with_group(name, selected_group, start_date.strftime("%Y-%m-%d")): cnt += 1
                    st.success(f"✅ {cnt}명 등록 완료!")
                    st.rerun()
                else:
                    st.warning("이름을 입력해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)
    
    # ----------------------------------------------------
    # 2. 조 변경 (일괄 변경 기능 복구)
    # ----------------------------------------------------
    with tab_change:
        st.info("💡 이름을 복사해 붙여넣고, 변경할 조와 날짜를 선택하면 일괄 변경됩니다.")
        c1, c2 = st.columns([3, 1])
        with c1:
            change_names_str = st.text_area("대상 승무원 목록 (엔터로 구분)", height=200, key="change_names_input", placeholder="홍길동\n김철수\n이영희")
        with c2:
            target_grp = st.selectbox("이동할 조", [f"{i}조" for i in range(1, 11)] + ["기타"], key="new_grp_bulk")
            st.markdown("<br>", unsafe_allow_html=True)
            change_date = st.date_input("변경 기준일", utils.get_kst_now().date(), key="eff_date_bulk")
            
            st.markdown('<div class="red-button">', unsafe_allow_html=True)
            if st.button("일괄 변경 적용", type="primary", use_container_width=True):
                if change_names_str:
                    names_to_change = [n.strip() for n in change_names_str.replace(',', '\n').split('\n') if n.strip()]
                    all_drivers = utils.load_data("drivers")
                    all_db_names = all_drivers['name'].astype(str).tolist() if not all_drivers.empty else []
                    
                    valid_names = []
                    invalid_names = []
                    
                    for name in names_to_change:
                        if name in all_db_names: valid_names.append(name)
                        else: invalid_names.append(name)
                    
                    if invalid_names: st.error(f"❌ 다음 이름은 명단에 없어 제외됩니다: {', '.join(invalid_names)}")
                    
                    if valid_names:
                        success_cnt = 0
                        for name in valid_names:
                            if utils.add_driver_with_group(name, target_grp, change_date.strftime("%Y-%m-%d")): success_cnt += 1
                        st.success(f"✅ {success_cnt}명의 조를 '{target_grp}'로 변경했습니다.")
                        st.balloons()
                    else: st.warning("변경할 유효한 대상이 없습니다.")
                else: st.warning("이름을 입력해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # 3. 퇴사 처리 (복구 + 삭제 버튼 추가)
    # ----------------------------------------------------
    with tab_resign:
        drivers = utils.load_data("drivers")
        # 이미 퇴사 처리된 사람도 목록에는 띄우되 구분 가능하게
        if not drivers.empty:
            active_list = drivers['name'].tolist()
            active_list.sort()
        else:
            active_list = []

        if active_list:
            st.write("승무원을 퇴사 처리하거나 데이터를 삭제합니다.")
            c_r1, c_r2 = st.columns(2)
            
            with c_r1: 
                r_target = st.selectbox("대상 승무원 선택", active_list, key="resign_dr")
                r_date = st.date_input("퇴사 일자", utils.get_kst_now().date(), key="resign_date")
                
                if st.button("👋 퇴사 처리 (재직상태 변경)", type="primary", key="btn_resign", use_container_width=True):
                    utils.set_driver_resignation(r_target, r_date.strftime("%Y-%m-%d"))
                    st.success(f"{r_target}님 퇴사 처리 완료")
                    st.rerun()

            with c_r2:
                st.write("⚠️ **데이터 완전 삭제**")
                st.caption("근무 기록과 조 배정 이력이 모두 삭제됩니다.")
                st.markdown('<div class="red-button">', unsafe_allow_html=True)
                if st.button("🗑️ 영구 삭제 (복구 불가)", key="btn_delete_dr", use_container_width=True):
                    utils.delete_driver(r_target)
                    st.error(f"{r_target}님 데이터 삭제 완료")
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        else: st.info("등록된 승무원이 없습니다.")

    # ----------------------------------------------------
    # 4. 관리자 계정 (완벽 복구)
    # ----------------------------------------------------
    with tab_users:
        st.write("### 🔐 관리자 및 직원 계정 관리")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        with c1: new_id = st.text_input("새 아이디")
        with c2: new_pw = st.text_input("새 비밀번호", type="password")
        with c3: new_role = st.selectbox("권한", ["admin", "staff"], format_func=lambda x: "관리자" if x == "admin" else "직원")
        with c3: new_name = st.text_input("사용자 이름")
        with c4:
            st.markdown("<br>", unsafe_allow_html=True) 
            if st.button("계정 생성", type="primary"):
                if new_id and new_pw and new_name:
                    if utils.add_user_account(new_id, new_pw, new_role, new_name):
                        st.success(f"계정 {new_id} 생성 완료"); st.rerun()
                    else: st.error("이미 존재하는 아이디입니다.")
                else: st.warning("모든 항목을 입력하세요.")
        
        st.divider()
        st.write("### 🔑 비밀번호 변경")
        users_df = utils.load_data("users")
        if not users_df.empty:
            c_pw1, c_pw2, c_pw3 = st.columns([3, 3, 1])
            with c_pw1: target_user_pw = st.selectbox("대상 계정 선택", users_df['username'].tolist())
            with c_pw2: target_new_pw = st.text_input("변경할 비밀번호", type="password", key="chg_pw_input")
            with c_pw3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("비밀번호 변경", type="primary"):
                    if target_new_pw:
                        if utils.update_user_password(target_user_pw, target_new_pw):
                            st.success(f"{target_user_pw}님의 비밀번호가 변경되었습니다.")
                        else: st.error("변경 실패")
                    else: st.warning("새 비밀번호를 입력하세요.")
        
        st.divider()
        st.write("📋 **등록된 계정 목록**")
        if not users_df.empty:
            for idx, row in users_df.iterrows():
                cc1, cc2, cc3, cc4, cc5 = st.columns([2, 2, 2, 2, 1])
                with cc1: st.write(f"**{row['username']}**")
                with cc2: st.write(row['name'])
                with cc3: st.write("관리자" if row['role']=='admin' else "직원")
                with cc4: st.write(row['created_at'])
                with cc5:
                    if row['username'] != 'admin':
                        if st.button("삭제", key=f"del_user_{row['username']}_{idx}"):
                            utils.delete_user_account(row['username'])
                            st.success("삭제됨"); st.rerun()

    # ----------------------------------------------------
    # [하단] 승무원 전체 명부 (상태 자동 계산 기능 추가)
    # ----------------------------------------------------
    st.divider()
    st.subheader("📋 전체 승무원 현황")
    
    drivers = utils.load_data("drivers")
    if not drivers.empty:
        search_dr = st.text_input("이름 검색", placeholder="이름을 입력하세요")
        if search_dr and 'name' in drivers.columns: 
            drivers = drivers[drivers['name'].str.contains(search_dr)]
            
        if 'resigned_date' in drivers.columns:
            # [수정된 로직] 퇴사일이 오늘 날짜보다 같거나 작으면 '퇴사'로 표시
            today_str = utils.get_kst_now().strftime("%Y-%m-%d")
            
            def get_status(date_val):
                d = str(date_val).strip()
                if not d: return "재직"
                return f"퇴사 ({d})" if d <= today_str else "재직"

            drivers['status_calc'] = drivers['resigned_date'].apply(get_status)
            
            # 재직자가 위로 오게 정렬
            drivers = drivers.sort_values(by=['status_calc', 'name'], ascending=[True, True])
            
            st.dataframe(
                drivers[['name', 'group_name', 'status_calc']], 
                hide_index=True, 
                use_container_width=True, 
                height=600,
                column_config={
                    "name": "이름",
                    "group_name": "현재 조",
                    "status_calc": "상태 (퇴사일)"
                }
            )
        else:
            st.dataframe(drivers, use_container_width=True)
    else:
        st.info("데이터가 없습니다.")
