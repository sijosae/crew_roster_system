import streamlit as st
import utils

def render_log_tab():
    st.subheader("🔧 시스템 로그 및 실행 취소")
    t_act, t_acc = st.tabs(["📋 작업 로그", "👥 접속 이력"])
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
        try:
            df_acc = utils.load_data("access_logs")
            if not df_acc.empty: st.dataframe(df_acc.sort_values(by='timestamp', ascending=False), use_container_width=True)
            else: st.info("접속 기록이 없습니다.")
        except: st.warning("로그 없음")
