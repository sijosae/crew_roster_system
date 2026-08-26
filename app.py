import streamlit as st
import extra_streamlit_components as stx
import utils
# 탭 모듈 임포트
from tabs import total_status, individual, input_mgr, driver_mgr, search, logs

def main():
    st.set_page_config(page_title="우진교통 배차 관리 시스템", layout="wide")
    utils.inject_custom_css()
    cookie_manager = stx.CookieManager(key="cookie_manager")

    if 'auth_status' not in st.session_state:
        st.session_state['auth_status'] = None

    # [세션 유지] 새로고침하면 session_state는 초기화되지만 쿠키는 남아있으므로,
    # 로그인 시 심어둔 토큰(쿠키)으로 다시 로그인 화면을 안 거치고 자동 로그인 처리.
    # 쿠키엔 무작위 토큰만 들어있고 실제 아이디/권한/이름은 서버 메모리에 있음(utils._session_store).
    if st.session_state['auth_status'] is None:
        token = cookie_manager.get("auth")
        if token:
            info = utils.verify_session_token(token)
            if info:
                st.session_state['auth_status'] = info['role']
                st.session_state['user_name'] = info['name']

    # [변경] st.empty()로 로그인 화면 자리를 잡아두면, 로그인 성공 시 st.rerun() 없이
    # 같은 스크립트 실행 안에서 이 자리를 지우고 바로 메인 화면으로 이어갈 수 있음.
    # (예전엔 rerun으로 페이지 구조 전체를 다시 그리면서 전환 순간 화면이 잠깐 멈춘 것처럼 보였음)
    login_area = st.empty()

    if st.session_state['auth_status'] is None:
        with login_area.container():
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1, 1])
            with c2:
                st.image("copyright_woojin.png", width=150)
                st.title("우진교통 배차 관리 시스템")
                with st.form("login_form"):
                    uid = st.text_input("아이디")
                    upw = st.text_input("비밀번호", type="password")
                    submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)

                if submitted:
                    user = utils.login_user(uid, upw)
                    if user:
                        st.session_state['auth_status'] = user[0]
                        st.session_state['user_name'] = user[1]
                        st.session_state['_pending_login_log'] = uid
                        new_token = utils.make_session_token(uid, user[0], user[1])
                        cookie_manager.set("auth", new_token, key="set_auth_cookie",
                                            max_age=utils.SESSION_MAX_AGE_DAYS * 86400)

                        # [핵심 수정] 로그인 성공 시 기존 날짜 정보 초기화 -> 오늘 날짜로 재설정됨
                        keys_to_clear = [
                            'view_year', 'view_month', 'sb_view_year', 'sb_view_month',
                            'indiv_view_year', 'indiv_view_month', 'sb_ind_year', 'sb_ind_month'
                        ]
                        for key in keys_to_clear:
                            if key in st.session_state:
                                del st.session_state[key]
                    else:
                        st.error("로그인 실패")

    if st.session_state['auth_status'] is None:
        return

    login_area.empty()

    # 메인 화면
    c_head1, c_head2 = st.columns([8, 1])
    with c_head1: st.title(f"우진교통 배차 관리 시스템 ({st.session_state.get('user_name')}님)")
    with c_head2:
        if st.button("로그아웃"):
            st.session_state['auth_status'] = None
            old_token = cookie_manager.get("auth")
            if old_token:
                utils.invalidate_session_token(old_token)
                cookie_manager.delete("auth", key="del_auth_cookie")
            # 로그아웃 시에도 깔끔하게 세션 정리
            keys_to_clear = [
                'view_year', 'view_month', 'sb_view_year', 'sb_view_month',
                'indiv_view_year', 'indiv_view_month', 'sb_ind_year', 'sb_ind_month'
            ]
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # [변경] 탭별로 스피너를 따로 두면 탭 사이 전환 순간에 스피너가 꺼졌다 켜지는 틈이 생겨서,
    # 전체 탭 렌더링을 하나의 스피너로 통째로 감쌈 (오른쪽 위 Running 표시와 지속시간을 맞춤)
    with st.spinner("불러오는 중..."):
        # 로그인 화면에서 미뤄뒀던 접속 로그 기록을 여기(이미 스피너가 떠 있는 상태)서 처리
        pending_uid = st.session_state.pop('_pending_login_log', None)
        if pending_uid:
            utils.log_login_access(pending_uid, st.session_state.get('user_name'))

        if st.session_state['auth_status'] == 'admin':
            t1, t2, t3, t4, t5, t6 = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력/배차", "⚙️ 승무원", "📊 조회", "🔧 로그"])
            with t1: total_status.render_calendar_tab(input_mgr.render_quick_input_content)
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
