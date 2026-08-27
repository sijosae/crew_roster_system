import streamlit as st
import utils

# 롤백을 지원하는 작업 종류 (utils.rollback_audit_entry 참고 - 시트마다 식별 방식이 달라서
# 지원하는 종류만 화이트리스트로 관리함)
_ROLLBACK_SUPPORTED = {
    'schedule_create', 'schedule_delete', 'schedule_update',
    'event_create', 'driver_create', 'driver_resign', 'driver_delete',
    'user_create', 'user_delete',
}

def render_log_tab():
    t_act, t_acc, t_migrate = st.tabs(["📋 작업 로그", "👥 접속 이력", "🔄 마이그레이션"])
    with t_act:
        st.caption("로그인 상태에서 이뤄진 생성/삭제/수정 작업이 전부 기록됩니다. 각 항목을 되돌릴 수 있습니다.")
        if st.button("📋 작업 로그 조회", key="btn_query_audit_log"):
            st.session_state['audit_log_queried'] = True
        if not st.session_state.get('audit_log_queried'):
            st.info("조회 버튼을 눌러주세요.")
        else:
            df_audit = utils.get_audit_log()
            if df_audit.empty:
                st.info("작업 기록이 없습니다.")
            else:
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
                                st.rerun()
                        else:
                            st.caption("-")
    with t_acc:
        # [최적화] 버튼을 누르기 전엔 access_logs를 아예 안 불러옴
        if st.button("👥 접속 이력 조회", key="btn_query_access_logs"):
            st.session_state['access_logs_queried'] = True
        if st.session_state.get('access_logs_queried'):
            try:
                df_acc = utils.load_data("access_logs")
                if not df_acc.empty: st.dataframe(df_acc.sort_values(by='timestamp', ascending=False), use_container_width=True)
                else: st.info("접속 기록이 없습니다.")
            except: st.warning("로그 없음")
    with t_migrate:
        st.write("예전 단일 `work_history` 시트를 연도별 시트(`work_history_2026` 등)로 나눠서 옮깁니다.")
        st.caption("이미 마이그레이션을 완료했다면 다시 눌러도 예전 시트가 없어서 아무 일도 일어나지 않습니다.")
        if st.button("🔄 work_history 마이그레이션 실행", type="primary"):
            with st.spinner("마이그레이션 중..."):
                result = utils.migrate_old_work_history()
            if result['status'] == 'done':
                st.success(f"✅ 완료: {result['count']}건을 연도별 시트로 옮겼습니다.")
            elif result['status'] == 'not_found':
                st.info("예전 work_history 시트가 없습니다 (이미 마이그레이션 완료됐거나, 처음부터 없었을 수 있습니다).")
            elif result['status'] == 'empty':
                st.info("예전 work_history 시트에 옮길 데이터가 없습니다.")

        st.divider()
        st.write("id가 비어있는 예전 승무원 등록자들에게 고유 id를 일괄로 부여합니다.")
        st.caption("이미 id가 있는 승무원은 건드리지 않습니다. 여러 번 눌러도 안전합니다.")
        if st.button("🔄 승무원 id 일괄 부여 실행", type="primary"):
            with st.spinner("처리 중..."):
                cnt = utils.backfill_driver_ids()
            if cnt:
                st.success(f"✅ 완료: {cnt}명에게 id를 새로 부여했습니다.")
            else:
                st.info("id가 비어있는 승무원이 없습니다.")
