import streamlit as st
import utils

def render_log_tab():
    st.subheader("🔧 시스템 로그 및 실행 취소")
    t_act, t_acc, t_migrate = st.tabs(["📋 작업 로그", "👥 접속 이력", "🔄 마이그레이션"])
    with t_act:
        if st.button("🗑️ 로그 비우기"): st.session_state['action_logs'] = []; st.rerun()
        st.divider()
        if 'action_logs' in st.session_state:
            for i, log in enumerate(st.session_state['action_logs']):
                c1, c2, c3 = st.columns([1, 4, 1])
                with c1: st.write(log['time'])
                with c2: st.write(f"{log['msg']}")
                with c3:
                    if log['status'] == 'active' and log.get('ids'):
                        if st.button("↩️ 실행 취소", key=f"undo_{i}"):
                            utils.delete_rows_by_ids(log['sheet'], log['ids'])
                            log['status'] = 'canceled'; st.rerun()
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
