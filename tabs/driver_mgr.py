import streamlit as st
import pandas as pd
import utils

_DRIVER_SUBMENU = ["승무원 등록", "조 변경", "퇴사 처리"]

@st.fragment
def render_driver_manage_tab():
    section = utils.render_submenu(_DRIVER_SUBMENU, "submenu_driver")
    if section == "조 변경":
        _render_group_change()
    elif section == "퇴사 처리":
        _render_resignation()
    else:
        _render_bulk_register()

    # ----------------------------------------------------
    # [하단] 승무원 전체 명부 (상태 자동 계산 기능 추가) - 서브메뉴와 무관하게 항상 표시
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

# ----------------------------------------------------
# 1. 승무원 등록 (일괄 등록 기능 복구)
# ----------------------------------------------------
def _render_bulk_register():
    st.info("💡 엑셀에서 이름을 복사해서 붙여넣으면 한 번에 등록됩니다.")
    with st.container(key="formbox_driver_add"):
        c1, c2 = st.columns([3, 1])
        with c1: bulk_names = st.text_area("승무원 성명 목록 (엔터로 구분)", height=150, placeholder="홍길동\n이철수\n박영희")
        with c2:
            selected_group = st.selectbox("소속 조", [f"{i}조" for i in range(1, 11)] + ["기타"])
            st.markdown("<br>", unsafe_allow_html=True)
            start_date = st.date_input("조 배정 시작일", utils.get_kst_now().date())

            if st.button("등록 실행", type="primary", use_container_width=True):
                if bulk_names:
                    names = [n.strip() for n in bulk_names.replace(',', '\n').split('\n') if n.strip()]
                    cnt = 0
                    for name in names:
                        if ',' in name or '\t' in name: parts = name.replace('\t', ',').split(','); name = parts[0].strip()
                        if utils.add_driver_with_group(name, selected_group, start_date.strftime("%Y-%m-%d")): cnt += 1
                    st.success(f"✅ {cnt}명 등록 완료!")
                    st.rerun(scope="fragment")
                else:
                    st.warning("이름을 입력해주세요.")

# ----------------------------------------------------
# 2. 조 변경 (일괄 변경 기능 복구)
# ----------------------------------------------------
def _render_group_change():
    st.info("💡 이름을 복사해 붙여넣고, 변경할 조와 날짜를 선택하면 일괄 변경됩니다.")
    with st.container(key="formbox_group_change"):
        c1, c2 = st.columns([1, 1])
        with c1:
            change_names_str = st.text_area("대상 승무원 목록 (엔터로 구분)", height=280, key="change_names_input", placeholder="홍길동\n김철수\n이영희")
        with c2:
            target_grp = st.selectbox("이동할 조", [f"{i}조" for i in range(1, 11)] + ["기타"], key="new_grp_bulk")
            st.markdown("<br>", unsafe_allow_html=True)
            change_date = st.date_input("변경 기준일", utils.get_kst_now().date(), key="eff_date_bulk")

            if st.button("일괄 변경 적용", type="primary", use_container_width=True):
                if change_names_str:
                    names_to_change = [n.strip() for n in change_names_str.replace(',', '\n').split('\n') if n.strip()]
                    all_drivers = utils.load_data("drivers")
                    # [수정] 대소문자 다르게 입력하면("김성근b") 명단에 있는 사람("김성근B")도
                    # 없는 걸로 취급되던 문제 - 대소문자 무시하고 비교하되, 실제 저장은 명단에
                    # 이미 있는 원래 표기 그대로 쓰도록 매핑해둠
                    name_map = {utils.norm_name(n): n for n in all_drivers['name'].astype(str)} if not all_drivers.empty else {}

                    valid_names = []
                    invalid_names = []

                    for name in names_to_change:
                        matched = name_map.get(utils.norm_name(name))
                        if matched: valid_names.append(matched)
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

# ----------------------------------------------------
# 3. 퇴사 처리 (복구 + 삭제 버튼 추가)
# ----------------------------------------------------
def _render_resignation():
    # [수정] 이름 대신 id로 처리하도록 변경 (동명이인/컬럼밀림 등으로 이름 매칭이 실패하던
    # 문제를 근본적으로 없앰). 화면엔 이름을 보여주되, 실제로 넘기는 값은 id.
    drivers = utils.load_data("drivers")
    driver_options, no_id_count = [], 0
    if not drivers.empty and 'id' in drivers.columns:
        drivers_sorted = drivers.sort_values(by='name')
        for _, row in drivers_sorted.iterrows():
            did = str(row['id']).strip()
            if did:
                driver_options.append((did, row['name']))
            else:
                no_id_count += 1

    if driver_options:
        if no_id_count:
            st.warning(f"⚠️ id가 없는 승무원 {no_id_count}명은 아래 목록에서 빠져있습니다. "
                       "'🔧 시스템 → 계정관리 옆 마이그레이션'에서 id를 부여해주세요.")
        st.caption("퇴사 처리는 재직 상태만 바꾸고, 영구 삭제는 근무 기록과 조 배정 이력까지 모두 지웁니다(복구 불가).")

        with st.container(key="formbox_resign"):
            c_sel, c_date, c_resign, c_del = st.columns([1.6, 1, 1, 1])
            with c_sel:
                r_target_id, r_target_name = st.selectbox(
                    "대상 승무원 선택", driver_options, format_func=lambda x: x[1], key="resign_dr"
                )
            with c_date:
                r_date = st.date_input("퇴사 일자", utils.get_kst_now().date(), key="resign_date")
            with c_resign:
                st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
                if st.button("👋 퇴사 처리", type="primary", key="btn_resign", use_container_width=True):
                    ok, msg = utils.set_driver_resignation(r_target_id, r_date.strftime("%Y-%m-%d"))
                    if ok:
                        # [참고] st.rerun() 직전엔 일반 메시지가 화면에 그려지기도 전에 사라지므로,
                        # 새로고침 이후에도 남는 st.toast로 띄움
                        st.toast(f"✅ {r_target_name}님 퇴사 처리: {msg}", icon="🔄")
                        st.rerun(scope="fragment")
                    else:
                        st.error(f"🚨 퇴사 처리 실패: {msg}")
            with c_del:
                st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
                if st.button("🗑️ 영구 삭제", key="btn_delete_dr", use_container_width=True):
                    ok, msg = utils.delete_driver(r_target_id)
                    if ok:
                        st.error(msg)
                        st.rerun(scope="fragment")
                    else:
                        st.warning(msg)
    else:
        st.info("등록된 승무원이 없습니다 (또는 전부 id가 비어있어 마이그레이션이 필요합니다).")
