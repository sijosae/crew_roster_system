import streamlit as st
import utils  # 공통 도구함
# 탭 모듈 임포트
from tabs import total_status, individual, input_mgr, driver_mgr, search, logs

def main():
    # 1. 페이지 기본 설정
    st.set_page_config(page_title="우진교통 배차 관리 시스템", layout="wide")
    
    # 2. CSS 스타일 주입
    utils.inject_custom_css()

    # 3. 로그인 상태 초기화
    if 'auth_status' not in st.session_state:
        st.session_state['auth_status'] = None

    # 4. 로그인 화면 렌더링
    if st.session_state['auth_status'] is None:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.title("우진교통 배차 관리 시스템")
            
            uid = st.text_input("아이디")
            upw = st.text_input("비밀번호", type="password")
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            
            if st.button("로그인", type="primary", use_container_width=True):
                # [수정] 비상 로그인 코드 삭제됨 -> 오직 DB 인증만 수행
                user = utils.login_user(uid, upw)
                if user:
                    st.session_state['auth_status'] = user[0] # role (admin/staff)
                    st.session_state['user_name'] = user[1]   # name
                    utils.log_login_access(uid, user[1])
                    st.rerun()
                else:
                    st.error("로그인 실패: 아이디 또는 비밀번호를 확인하세요.")
            st.markdown('</div>', unsafe_allow_html=True)
        return

    # 5. 메인 앱 화면 (로그인 성공 후)
    c_head1, c_head2 = st.columns([8, 1])
    with c_head1:
        st.title(f"우진교통 배차 관리 시스템 ({st.session_state.get('user_name')}님)")
    with c_head2:
        if st.button("로그아웃"):
            st.session_state['auth_status'] = None
            st.rerun()

    # 6. 권한별 탭 구성 및 모듈 호출
    if st.session_state['auth_status'] == 'admin':
        t1, t2, t3, t4, t5, t6 = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력/배차", "⚙️ 승무원", "📊 조회", "🔧 로그"])
        
        with t1: total_status.render_calendar_tab()
        with t2: individual.render_individual_calendar_tab()
        with t3: input_mgr.render_input_tab()
        with t4: driver_mgr.render_driver_manage_tab()
        with t5: search.render_view_manage_tab()
        with t6: logs.render_log_tab()
    else:
        # 일반 직원용 탭 구성
        t1, t2, t3 = st.tabs(["📅 전체 현황", "👤 개인별", "📊 조회"])
        
        with t1: total_status.render_calendar_tab()
        with t2: individual.render_individual_calendar_tab()
        with t3: search.render_public_search_tab()

if __name__ == '__main__':
    main()
