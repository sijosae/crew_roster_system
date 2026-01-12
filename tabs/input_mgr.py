import streamlit as st
import pandas as pd
from datetime import datetime
import time
import traceback
import utils  # 공통 도구함

# ==========================================
# 1. 빠른 등록 다이얼로그 (팝업창)
# ==========================================
@st.dialog("➕ 빠른 등록")
def show_input_dialog():
    tab1, tab2 = st.tabs(["👤 승무원 일정", "🏢 회사 행사"])
    
    # 탭 1: 승무원 일정
    with tab1:
        st.write("달력을 보면서 바로 입력하세요.")
        names_str = st.text_area("이름 (엔터 구분)", height=100, key="quick_names")
        rng = st.date_input("기간", [], help="시작/종료일 선택", key="quick_range")
        
        c1, c2 = st.columns(2)
        with c1: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="quick_type")
        with c2: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="quick_shift")
        nte = st.text_input("비고", key="quick_note")
        
        if st.button("승무원 일정 저장", type="primary", use_container_width=True):
            if names_str and len(rng) > 0:
                lst = [n.strip() for n in names_str.replace(',', '\n').split('\n') if n.strip()]
                try:
                    with st.spinner('저장 중...'):
                        count, ids = utils.save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
                    
                    st.toast("✅ 저장 완료!", icon="🔄")
                    utils.add_log(f"입력 성공: {len(lst)}명", ids=ids, sheet_name="schedules")
                    # [수정] 대기 시간(time.sleep) 제거 -> 즉시 닫힘
                    st.rerun()
                except Exception as e:
                    st.error(f"🚨 저장 중 오류 발생: {e}")
            else:
                st.warning("이름과 기간을 입력해주세요.")
                
    # 탭 2: 회사 행사
    with tab2:
        st.write("회사 주요 행사를 달력 상단에 표시합니다.")
        ed_list = st.date_input("행사 기간", [], help="시작/종료일", key="quick_event_range")
        et = st.text_input("행사 내용", key="quick_event_title")
        
        if st.button("회사 행사 저장", type="primary", use_container_width=True, key="quick_event_save"):
            if et and len(ed_list) > 0:
                try:
                    with st.spinner('저장 중...'):
                        for d in pd.date_range(ed_list[0], ed_list[-1]):
                            utils.add_company_event(d.strftime("%Y-%m-%d"), et)
                        st.cache_data.clear()
                        
                    st.toast("✅ 행사 저장 완료!", icon="🔄")
                    utils.add_log(f"행사 등록: {et}", sheet_name="company_events")
                    # [수정] 대기 시간 제거 -> 즉시 닫힘
                    st.rerun()
                except Exception:
                    st.error("오류 발생")
            else:
                st.warning("기간과 내용을 입력해주세요.")

# ==========================================
# 2. 메인 입력 탭 렌더링 함수
# ==========================================
def render_input_tab():
    st.subheader("📝 관리자 입력 & 배차 관리")
    t1, t2, t3, t4 = st.tabs(["휴무 등록", "행사 등록", "📂 배차일지 업로드", "⚙️ 감차 규칙"])
    
    # --- 1. 휴무 등록 ---
    with t1:
        c1, c2 = st.columns([2, 1])
        with c1: names_str = st.text_area("이름 (엔터 구분)", height=68, key="tab_names")
        with c2: rng = st.date_input("기간", [], help="시작/종료일 선택", key="tab_range")
        
        c3, c4 = st.columns(2)
        with c3: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="tab_type")
        with c4: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="tab_shift")
        nte = st.text_input("비고", key="tab_note")
        
        st.markdown('<div class="red-button">', unsafe_allow_html=True)
        if st.button("일괄 저장", type="primary", use_container_width=True):
            if names_str and len(rng) > 0:
                try:
                    with st.spinner('저장...'):
                        lst = [n.strip() for n in names_str.split('\n') if n.strip()]
                        utils.save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
                    st.success("완료")
                    st.rerun()
                except: st.error("오류")
    
    # --- 2. 행사 등록 ---
    with t2:
        ed = st.date_input("행사 기간", [], key="evt_rng")
        et = st.text_input("내용", key="evt_tit")
        if st.button("행사 저장"):
            if et and len(ed) > 0:
                for d in pd.date_range(ed[0], ed[-1]):
                    utils.add_company_event(d.strftime("%Y-%m-%d"), et)
                st.cache_data.clear()
                st.success("저장됨")
                st.rerun()
                
    # --- 3. 배차일지 업로드 ---
    with t3:
        st.info("💡 여러 개의 엑셀 파일을 한 번에 업로드하면 근무 이력을 자동 분석하여 DB에 저장합니다.")
        up_files = st.file_uploader("배차일지 엑셀 파일 (.xlsx)", type=['xlsx'], accept_multiple_files=True)
        
        if up_files:
            if st.button("분석 및 DB 저장 실행", type="primary"):
                with st.spinner(f"{len(up_files)}개 파일 분석 중... (시간이 조금 걸립니다)"):
                    try:
                        all_dfs = []
                        for up_file in up_files:
                            # utils의 함수 사용
                            df_res = utils.parse_roster_excel(up_file)
                            all_dfs.append(df_res)
                        
                        if all_dfs:
                            final_df = pd.concat(all_dfs, ignore_index=True)
                            cnt = utils.save_work_history(final_df)
                            st.success(f"✅ {len(up_files)}개 파일에서 총 {cnt}건의 신규 근무 이력이 저장/갱신되었습니다!")
                        else:
                            st.warning("분석할 데이터가 없습니다.")
                            
                    except Exception as e:
                        st.error(f"실패: {e}")
                        st.code(traceback.format_exc())
                        
    # --- 4. 감차 규칙 설정 ---
    with t4:
        st.write("### 🛑 운행 감축(Reduction) 규칙 설정")
        c_r1, c_r2 = st.columns(2)
        with c_r1: 
            g_start = st.date_input("시작일", value=datetime(2025,1,1))
            g_end = st.date_input("종료일", value=datetime(2025,12,31))
        with c_r2:
            g_route = st.text_input("노선 번호 (예: 211)")
            g_seq = st.text_input("순번 (예: 3)")
            g_cond = st.selectbox("적용 조건", ["Weekend/Holiday", "Always"])
        
        if st.button("규칙 추가"):
            if g_route and g_seq:
                utils.add_reduction_rule(g_start, g_end, g_route, g_seq, g_cond)
                st.success("규칙 추가됨")
                st.rerun()
        
        st.divider()
        try:
            rules_df = utils.load_data("reduction_rules")
            if not rules_df.empty:
                st.dataframe(rules_df)
        except:
            st.caption("등록된 규칙 없음")
