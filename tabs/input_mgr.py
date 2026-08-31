import streamlit as st
import pandas as pd
from datetime import datetime
import traceback
import utils  # 공통 도구함

# ==========================================
# 1. 빠른 등록 - 인라인 패널
# ==========================================
# [변경] 원래 @st.dialog(모달 팝업)였으나, 모달을 여는 순간 뒷배경 페이지 전체가
# 다시 렌더링되는 Streamlit의 구조적 특성 때문에 total_status.py의 @st.fragment 버튼
# 안에서 호출되는 "인라인 패널"로 바꿈 (뒷배경을 전혀 건드리지 않고 그 자리에서 펼쳐짐)
_QUICK_INPUT_SUBMENU = ["승무원 일정", "회사 행사"]

def render_quick_input_content(modal_slot=None):
    section = utils.render_submenu(_QUICK_INPUT_SUBMENU, "submenu_quickinput")

    if section == "회사 행사":
        _render_quick_event(modal_slot)
    else:
        _render_quick_schedule(modal_slot)

def _render_quick_schedule(modal_slot):
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
            invalid = utils.validate_driver_names(lst)
            dup = utils.check_duplicate_schedule(lst, rng[0], rng[-1]) if not invalid else []
            if invalid:
                st.error(f"🚨 등록되지 않은 승무원입니다: {', '.join(invalid)}")
            elif dup:
                dup_txt = ', '.join(f"{n}({d})" for n, d in dup)
                st.error(f"🚨 이미 등록된 휴무입니다: {dup_txt}")
            else:
                try:
                    with st.spinner('저장 중...'):
                        count, ids = utils.save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)

                    st.toast("✅ 저장 완료!", icon="🔄")
                    st.session_state['show_quick_input'] = False
                    # [변경] 전체 새로고침(로딩 화면)이 뜨기 전에 모달부터 먼저 닫음
                    if modal_slot: modal_slot.empty()
                    # [최적화] 전체 앱이 아니라 이 탭(fragment)만 다시 그림
                    st.rerun(scope="fragment")
                except Exception as e:
                    st.error(f"🚨 저장 중 오류 발생: {e}")
        else:
            st.warning("이름과 기간을 입력해주세요.")

def _render_quick_event(modal_slot):
    st.write("회사 주요 행사를 달력 상단에 표시합니다.")
    ed_list = st.date_input("행사 기간", [], help="시작/종료일", key="quick_event_range")
    et = st.text_input("행사 내용", key="quick_event_title")

    if st.button("회사 행사 저장", type="primary", use_container_width=True, key="quick_event_save"):
        if et and len(ed_list) > 0:
            try:
                with st.spinner('저장 중...'):
                    for d in pd.date_range(ed_list[0], ed_list[-1]):
                        # add_company_event 내부에서 이미 company_events 캐시만 선택적으로 지움
                        utils.add_company_event(d.strftime("%Y-%m-%d"), et)

                st.toast("✅ 행사 저장 완료!", icon="🔄")
                st.session_state['show_quick_input'] = False
                # [변경] 전체 새로고침(로딩 화면)이 뜨기 전에 모달부터 먼저 닫음
                if modal_slot: modal_slot.empty()
                # [최적화] 전체 앱이 아니라 이 탭(fragment)만 다시 그림
                st.rerun(scope="fragment")
            except Exception:
                st.error("오류 발생")
        else:
            st.warning("기간과 내용을 입력해주세요.")

# ==========================================
# 2. 메인 입력 탭 렌더링 함수
# ==========================================
_INPUT_SUBMENU = ["휴무 등록", "행사 등록", "배차일지 업로드", "감차 규칙"]

@st.fragment
def render_input_tab():
    section = utils.render_submenu(_INPUT_SUBMENU, "submenu_input")
    if section == "행사 등록":
        _render_event_register()
    elif section == "배차일지 업로드":
        _render_roster_upload()
    elif section == "감차 규칙":
        _render_reduction_rules()
    else:
        _render_leave_register()

# --- 1. 휴무 등록 ---
def _render_leave_register():
    with st.container(key="formbox_leave"):
        c1, c2 = st.columns([1, 1.2])
        with c1:
            names_str = st.text_area("이름 (엔터 구분)", height=180, key="tab_names")
        with c2:
            rng = st.date_input("기간", [], help="시작/종료일 선택", key="tab_range")
            typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="tab_type")
            sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="tab_shift")
        nte = st.text_input("비고", key="tab_note")

        if st.button("일괄 저장", type="primary"):
            if names_str and len(rng) > 0:
                lst = [n.strip() for n in names_str.split('\n') if n.strip()]
                invalid = utils.validate_driver_names(lst)
                dup = utils.check_duplicate_schedule(lst, rng[0], rng[-1]) if not invalid else []
                if invalid:
                    st.error(f"🚨 등록되지 않은 승무원입니다: {', '.join(invalid)}")
                elif dup:
                    dup_txt = ', '.join(f"{n}({d})" for n, d in dup)
                    st.error(f"🚨 이미 등록된 휴무입니다: {dup_txt}")
                else:
                    try:
                        with st.spinner('저장...'):
                            utils.save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
                        st.success("완료")
                        st.rerun(scope="fragment")
                    except: st.error("오류")

# --- 2. 행사 등록 ---
def _render_event_register():
    with st.container(key="formbox_event"):
        c1, _ = st.columns([1, 1.4])
        with c1:
            ed = st.date_input("행사 기간", [], key="evt_rng")
        et = st.text_area("내용", key="evt_tit", height=120)
        if st.button("행사 저장"):
            if et and len(ed) > 0:
                for d in pd.date_range(ed[0], ed[-1]):
                    utils.add_company_event(d.strftime("%Y-%m-%d"), et)
                st.cache_data.clear()
                st.success("저장됨")
                st.rerun(scope="fragment")

# --- 3. 배차일지 업로드 ---
def _render_roster_upload():
    st.info("💡 엑셀 파일(.xlsx, .xlsm)을 업로드하면 근무 이력을 자동 분석하여 DB에 저장합니다.")

    # [수정] type=['xlsx', 'xlsm'] 추가하여 매크로 파일 허용
    up_files = st.file_uploader("배차일지 엑셀 파일", type=['xlsx', 'xlsm'], accept_multiple_files=True)

    if up_files:
        if st.button("분석 및 DB 저장 실행", type="primary"):
            with st.spinner(f"{len(up_files)}개 파일 분석 중... (시간이 조금 걸립니다)"):
                try:
                    all_dfs = []
                    for up_file in up_files:
                        # utils의 함수 사용 (xlsm도 내부 엔진이 알아서 처리함)
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
def _render_reduction_rules():
    st.write("### 🛑 운행 감축(Reduction) 규칙 설정")
    c_start, c_end, c_route, c_seq, c_cond, c_btn = st.columns([1.2, 1.2, 1, 0.8, 1.2, 0.9])
    with c_start:
        g_start = st.date_input("시작일", value=datetime(2025,1,1))
    with c_end:
        g_end = st.date_input("종료일", value=datetime(2025,12,31))
    with c_route:
        g_route = st.text_input("노선 번호 (예: 211)")
    with c_seq:
        g_seq = st.text_input("순번 (예: 3)")
    with c_cond:
        g_cond = st.selectbox("적용 조건", ["Weekend/Holiday", "Always"])
    with c_btn:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if st.button("규칙 추가"):
            if g_route and g_seq:
                utils.add_reduction_rule(g_start, g_end, g_route, g_seq, g_cond)
                st.success("규칙 추가됨")
                st.rerun(scope="fragment")

    st.divider()
    # [최적화] 버튼을 누르기 전엔 reduction_rules를 아예 안 불러옴
    if st.button("📋 등록된 규칙 조회", key="btn_query_rules"):
        st.session_state['rules_queried'] = True
    if st.session_state.get('rules_queried'):
        try:
            rules_df = utils.load_data("reduction_rules")
            if not rules_df.empty:
                st.dataframe(rules_df)
        except:
            st.caption("등록된 규칙 없음")
