import streamlit as st
import utils
# 탭 모듈 임포트
from tabs import total_status, individual, input_mgr, driver_mgr, search, logs

def main():
    st.set_page_config(page_title="우진교통 배차 관리 시스템", layout="wide")
    utils.inject_custom_css()

    if 'auth_status' not in st.session_state:
        st.session_state['auth_status'] = None

    # 로그인 화면
    if st.session_state['auth_status'] is None:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.title("우진교통 배차 관리 시스템")
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            
            if st.button("로그인", type="primary", use_container_width=True):
                user = utils.login_user(uid, upw)
                if user:
                    st.session_state['auth_status'] = user[0]
                    st.session_state['user_name'] = user[1]
                    utils.log_login_access(uid, user[1])
                    
                    # [핵심 수정] 로그인 성공 시 기존 날짜 정보 초기화 -> 오늘 날짜로 재설정됨
                    keys_to_clear = [
                        'view_year', 'view_month', 'sb_view_year', 'sb_view_month',
                        'indiv_view_year', 'indiv_view_month', 'sb_ind_year', 'sb_ind_month'
                    ]
                    for key in keys_to_clear:
                        if key in st.session_state:
                            del st.session_state[key]
                            
                    st.rerun()
                else:
                    st.error("로그인 실패")
            st.markdown('</div>', unsafe_allow_html=True)
        return

    # 메인 화면
    c_head1, c_head2 = st.columns([8, 1])
    with c_head1: st.title(f"우진교통 배차 관리 시스템 ({st.session_state.get('user_name')}님)")
    with c_head2: 
        if st.button("로그아웃"): 
            st.session_state['auth_status'] = None
            # 로그아웃 시에도 깔끔하게 세션 정리
            keys_to_clear = [
                'view_year', 'view_month', 'sb_view_year', 'sb_view_month',
                'indiv_view_year', 'indiv_view_month', 'sb_ind_year', 'sb_ind_month'
            ]
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    if st.session_state['auth_status'] == 'admin':
        t1, t2, t3, t4, t5, t6 = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력/배차", "⚙️ 승무원", "📊 조회", "🔧 로그"])
        with t1: total_status.render_calendar_tab(input_mgr.show_input_dialog)
        with t2: individual.render_individual_calendar_tab()
        with t3: input_mgr.render_input_tab()
        with t4: driver_mgr.render_driver_manage_tab()
        with t5: search.render_view_manage_tab()
        with t6: logs.render_log_tab()
    else:
        t1, t2, t3 = st.tabs(["📅 전체 현황", "👤 개인별", "📊 조회"])
        with t1: total_status.render_calendar_tab(None)
        with t2: individual.render_individual_calendar_tab()
        with t3: search.render_public_search_tab()

if __name__ == '__main__':
    main()
