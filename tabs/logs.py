import streamlit as st
import utils

# 롤백을 지원하는 작업 종류 (utils.rollback_audit_entry 참고 - 시트마다 식별 방식이 달라서
# 지원하는 종류만 화이트리스트로 관리함)
_ROLLBACK_SUPPORTED = {
    'schedule_create', 'schedule_delete', 'schedule_update',
    'event_create', 'driver_create', 'driver_resign', 'driver_delete',
    'user_create', 'user_delete',
}

_LOG_SUBMENU = ["작업 로그", "접속 이력", "계정관리", "마이그레이션"]

@st.fragment
def render_log_tab():
    section = utils.render_submenu(_LOG_SUBMENU, "submenu_logs")
    if section == "접속 이력":
        _render_access_log()
    elif section == "계정관리":
        _render_user_accounts()
    elif section == "마이그레이션":
        _render_migration()
    else:
        _render_action_log()

def _render_action_log():
    st.caption("로그인 상태에서 이뤄진 생성/삭제/수정 작업이 전부 기록됩니다. 각 항목을 되돌릴 수 있습니다.")
    if st.button("작업 로그 조회", key="btn_query_audit_log"):
        st.session_state['audit_log_queried'] = True
    if not st.session_state.get('audit_log_queried'):
        st.info("조회 버튼을 눌러주세요.")
        return
    df_audit = utils.get_audit_log()
    if df_audit.empty:
        st.info("작업 기록이 없습니다.")
        return
    df_audit = df_audit.sort_values(by='timestamp', ascending=False)
    st.divider()
    h1, h2, h3, h4, h5 = st.columns([1.6, 1, 1.2, 2.6, 1.2])
    for h, label in zip((h1, h2, h3, h4), ("시간", "승무원", "일자", "작업내용")):
        with h: st.caption(f"**{label}**")
    for _, row in df_audit.iterrows():
        name_disp, date_disp = utils.summarize_audit_entry(row.get('before', ''), row.get('after', ''))
        c1, c2, c3, c4, c5 = st.columns([1.6, 1, 1.2, 2.6, 1.2])
        with c1: st.caption(row.get('timestamp', ''))
        with c2: st.caption(name_disp)
        with c3: st.caption(date_disp)
        with c4: st.write(row.get('summary', ''))
        with c5:
            is_rolled_back = str(row.get('rolled_back', '')).strip().upper() == 'Y'
            action = row.get('action', '')
            if action == 'rollback':
                st.caption("↩️ 롤백 기록")
            elif is_rolled_back:
                st.caption("✅ 롤백됨")
            elif action in _ROLLBACK_SUPPORTED:
                if st.button("↩️ 롤백", key=f"rollback_{row['id']}"):
                    ok, msg = utils.rollback_audit_entry(row['id'])
                    if ok:
                        st.toast(f"✅ {msg}", icon="🔄")
                    else:
                        st.warning(msg)
                    st.rerun(scope="fragment")
            else:
                st.caption("-")

def _render_access_log():
    # [최적화] 버튼을 누르기 전엔 access_logs를 아예 안 불러옴
    if st.button("접속 이력 조회", key="btn_query_access_logs"):
        st.session_state['access_logs_queried'] = True
    if st.session_state.get('access_logs_queried'):
        try:
            df_acc = utils.load_data("access_logs")
            if not df_acc.empty: st.dataframe(df_acc.sort_values(by='timestamp', ascending=False), use_container_width=True)
            else: st.info("접속 기록이 없습니다.")
        except: st.warning("로그 없음")

def _render_user_accounts():
    st.write("### 🔐 관리자 및 직원 계정 관리")
    with st.container(key="formbox_account_create"):
        new_id = st.text_input("아이디")
        new_pw = st.text_input("비밀번호", type="password")
        new_name = st.text_input("사용자 이름")
        c_role, c_btn = st.columns([2, 1])
        with c_role:
            new_role = st.selectbox("권한", ["admin", "staff"], format_func=lambda x: "관리자" if x == "admin" else "직원")
        with c_btn:
            st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
            if st.button("계정 생성", type="primary", use_container_width=True):
                if new_id and new_pw and new_name:
                    if utils.add_user_account(new_id, new_pw, new_role, new_name):
                        st.success(f"계정 {new_id} 생성 완료"); st.rerun(scope="fragment")
                    else: st.error("이미 존재하는 아이디입니다.")
                else: st.warning("모든 항목을 입력하세요.")

    st.divider()
    st.write("### 🔑 비밀번호 변경")
    users_df = utils.load_data("users")
    if not users_df.empty:
        with st.container(key="formbox_account_pw"):
            target_user_pw = st.selectbox("대상 계정 선택", users_df['username'].tolist())
            target_new_pw = st.text_input("새 비밀번호", type="password", key="chg_pw_input")
            if st.button("비밀번호 변경", type="primary"):
                if target_new_pw:
                    if utils.update_user_password(target_user_pw, target_new_pw):
                        st.success(f"{target_user_pw}님의 비밀번호가 변경되었습니다.")
                    else: st.error("변경 실패")
                else: st.warning("새 비밀번호를 입력하세요.")

    st.divider()
    st.write("📋 **등록된 계정 목록**")

    confirm_user = st.session_state.get('confirm_delete_user')
    if confirm_user:
        st.warning(f"'{confirm_user}' 삭제하시겠습니까?")
        c_ok, c_cancel = st.columns(2)
        with c_ok:
            if st.button("확인", type="primary", key="confirm_del_user_ok", use_container_width=True):
                utils.delete_user_account(confirm_user)
                st.session_state['confirm_delete_user'] = None
                st.success("삭제됨"); st.rerun(scope="fragment")
        with c_cancel:
            if st.button("취소", key="confirm_del_user_cancel", use_container_width=True):
                st.session_state['confirm_delete_user'] = None
                st.rerun(scope="fragment")

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
                        st.session_state['confirm_delete_user'] = row['username']
                        st.rerun(scope="fragment")

def _render_migration():
    st.write("id가 비어있는 예전 승무원 등록자들에게 고유 id를 일괄로 부여합니다.")
    st.caption("이미 id가 있는 승무원은 건드리지 않습니다. 여러 번 눌러도 안전합니다.")
    if st.button("승무원 id 일괄 부여 실행", type="primary"):
        with st.spinner("처리 중..."):
            cnt = utils.backfill_driver_ids()
        if cnt:
            st.success(f"✅ 완료: {cnt}명에게 id를 새로 부여했습니다.")
        else:
            st.info("id가 비어있는 승무원이 없습니다.")

    st.divider()
    _render_data_diagnosis()

def _render_data_diagnosis():
    st.write("### 🔍 이상데이터 진단 / 정리")
    st.caption("예전 배차일지 파서 버그와 예전 일정(schedules) id 생성 버그로 시트에 이미 쌓여있는 이상 데이터를 찾아서 보여주고, 확인 후 정리할 수 있습니다.")
    if st.button("진단 실행", key="btn_diagnose"):
        with st.spinner("점검 중... (시트가 크면 시간이 좀 걸립니다)"):
            st.session_state['data_diagnosis'] = utils.diagnose_data_issues()

    diag = st.session_state.get('data_diagnosis')
    if diag is None:
        st.info("진단 버튼을 눌러주세요.")
        return
    if not diag:
        st.success("✅ 확인된 이상 데이터가 없습니다.")
        return

    if 'drivers_blank_id' in diag:
        d = diag['drivers_blank_id']
        more = " 외" if d['count'] > len(d['sample']) else ""
        st.warning(f"👤 승무원 id 빈 값 {d['count']}명: {', '.join(d['sample'])}{more}")
        st.caption("→ 위쪽 '승무원 id 일괄 부여 실행' 버튼으로 정리할 수 있습니다.")

    if 'schedules_id' in diag:
        d = diag['schedules_id']
        st.warning(f"📅 일정(schedules) id 중복 {d['dup_id_count']}개({d['dup_row_count']}행), 빈 id {d['blank_count']}행")
        st.caption("→ id로 특정 행을 찾아 수정/삭제하는 기능이 엉뚱한 행을 건드릴 수 있는 위험이 있습니다.")
        if st.button("일정 id 중복/빈 값 정리", key="btn_fix_sched_id"):
            with st.spinner("정리 중..."):
                cnt = utils.fix_schedule_id_issues()
            st.success(f"✅ {cnt}건에 새 고유 id를 부여했습니다.")
            st.session_state.pop('data_diagnosis', None)
            st.rerun(scope="fragment")

    if 'schedules_invalid_names' in diag:
        d = diag['schedules_invalid_names']
        more = " 외" if d['count'] > len(d['sample']) else ""
        st.warning(f"🚫 일정에 승무원 명단에 없는 이름(이상등록자) {d['count']}명: {', '.join(d['sample'])}{more}")
        st.caption("→ '휴무 현황 > 개인 현황'에서 '이상등록자' 항목으로 확인/삭제할 수 있습니다.")

    if 'schedules_dup_registration' in diag:
        d = diag['schedules_dup_registration']
        st.warning(f"♻️ 동일 (이름,날짜) 중복 등록 {d['row_count']}행 (중복 조합 {d['combo_count']}개)")
        st.caption("→ '휴무 현황 > 개인 현황'에서 대상자별로 확인 후 정리해주세요.")

    if 'group_history_orphan' in diag:
        d = diag['group_history_orphan']
        st.info(f"ℹ️ 조 변경 이력에 현재 승무원 명단에 없는 이름 {d['count']}명: {', '.join(d['sample'])} (퇴사/삭제된 승무원의 이력으로 보이며, 화면 표시에 큰 영향은 없습니다)")

    if 'work_history' in diag:
        st.warning("🚌 근무이력(work_history) 시트에 예전 파서 버그로 섞여 들어간 것으로 보이는 이상 행이 있습니다:")
        for year, info in sorted(diag['work_history'].items()):
            st.write(f"- **{year}년**: 전체 {info['total']}행 중 쓰레기 행 {info['garbage']}건, (날짜,차량,근무) 중복 {info['dup']}건")
        st.caption("정리하면 이름 빈칸 / 차량번호(5001~5300) 범위 밖 / 노선 텍스트가 비정상적으로 긴 행을 삭제하고, 같은 (날짜,차량,근무) 중복은 최신 것만 남깁니다. **삭제는 되돌릴 수 없으니**, 원본 배차일지 파일이 있다면 재업로드하는 쪽을 더 권장합니다.")
        for year in sorted(diag['work_history'].keys()):
            if st.button(f"{year}년 이상데이터 정리", key=f"btn_clean_wh_{year}"):
                with st.spinner(f"{year}년 정리 중..."):
                    removed, before = utils.clean_work_history_garbage(year)
                st.success(f"✅ {year}년: 전체 {before}행 중 {removed}행 정리했습니다.")
                st.session_state.pop('data_diagnosis', None)
                st.rerun(scope="fragment")
