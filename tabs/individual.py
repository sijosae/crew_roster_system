import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
import io
import utils  # 공통 도구함

# ==========================================
# 1. 탭 내부 전용 콜백 함수
# ==========================================
def prev_month_indiv():
    if st.session_state.indiv_view_month == 1:
        st.session_state.indiv_view_year -= 1
        st.session_state.indiv_view_month = 12
    else:
        st.session_state.indiv_view_month -= 1
    st.session_state.sb_ind_year = st.session_state.indiv_view_year
    st.session_state.sb_ind_month = st.session_state.indiv_view_month

def next_month_indiv():
    if st.session_state.indiv_view_month == 12:
        st.session_state.indiv_view_year += 1
        st.session_state.indiv_view_month = 1
    else:
        st.session_state.indiv_view_month += 1
    st.session_state.sb_ind_year = st.session_state.indiv_view_year
    st.session_state.sb_ind_month = st.session_state.indiv_view_month

# ==========================================
# 2. 메인 렌더링 함수
# ==========================================
def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황 (통합)")
    
    # 1. 데이터 로드
    drivers = utils.load_data("drivers")
    if drivers.empty:
        st.warning("등록된 승무원이 없습니다.")
        return
    
    df_plan = utils.load_data("schedules")
    df_work = utils.load_data("work_history")
    reduction_rules = utils.get_reduction_rules()
    
    if df_work.empty:
        df_work = pd.DataFrame(columns=['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub'])
    else:
        required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub']
        for c in required_cols:
            if c not in df_work.columns: df_work[c] = ""

    now = utils.get_kst_now()

    # 2. 날짜 상태 초기화
    if 'indiv_view_year' not in st.session_state: 
        st.session_state.indiv_view_year = now.year
    if 'indiv_view_month' not in st.session_state: 
        st.session_state.indiv_view_month = now.month
    
    # 3. 컨트롤 패널
    c_nm, c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([2, 0.4, 0.8, 0.3, 0.7, 0.4, 0.4])
    
    with c_nm: 
        target = st.selectbox("승무원 선택", drivers['name'].tolist(), key='sel_driver', label_visibility="collapsed")
    
    with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        year_range = range(2023, now.year + 3)
        try: y_idx = list(year_range).index(st.session_state.indiv_view_year)
        except: y_idx = 0
        selected_year = st.selectbox("년도", year_range, index=y_idx, key='sb_ind_year', label_visibility="collapsed")
        if selected_year != st.session_state.indiv_view_year:
            st.session_state.indiv_view_year = selected_year
            st.rerun()

    with c_mo_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c_mo: 
        month_range = range(1, 13)
        selected_month = st.selectbox("월", month_range, index=st.session_state.indiv_view_month - 1, key='sb_ind_month', label_visibility="collapsed")
        if selected_month != st.session_state.indiv_view_month:
            st.session_state.indiv_view_month = selected_month
            st.rerun()

    with c_prev: st.button("◀", key="i_prev_btn", on_click=prev_month_indiv)
    with c_next: st.button("▶", key="i_next_btn", on_click=next_month_indiv)
    
    st.divider()

    # 4. 달력 및 리스트 데이터 준비
    if target:
        year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
        filter_ym = f"{year}-{month:02d}"
        
        # 해당 월 데이터 필터링
        my_plan = df_plan[(df_plan['name']==target) & (df_plan['date'].astype(str).str.startswith(filter_ym))] if not df_plan.empty else pd.DataFrame()
        my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))] if not df_work.empty else pd.DataFrame()
        
        # 연간 통계용
        y_filter = f"{year}-"
        y_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(y_filter))] if not df_work.empty else pd.DataFrame()
        
        # 통계 계산
        stats_am = len(my_work[my_work['shift'] == '오전']) if not my_work.empty else 0
        stats_pm = len(my_work[my_work['shift'] == '오후']) if not my_work.empty else 0
        y_am = len(y_work[y_work['shift'] == '오전']) if not y_work.empty else 0
        y_pm = len(y_work[y_work['shift'] == '오후']) if not y_work.empty else 0
        
        # 상단 통계 배지
        st.markdown(f"""
        <div style='display:flex; justify-content:center; gap:20px; margin-bottom:15px;'>
            <div style='background:#E3F2FD; padding:10px 20px; border-radius:10px; text-align:center; border:1px solid #90CAF9;'>
                <div style='font-size:12px; font-weight:bold; color:#1565C0;'>📅 {month}월 근무</div>
                <div style='font-size:14px;'>오전 <span style='color:blue; font-weight:bold;'>{stats_am}</span> / 오후 <span style='color:red; font-weight:bold;'>{stats_pm}</span></div>
            </div>
            <div style='background:#FFF3E0; padding:10px 20px; border-radius:10px; text-align:center; border:1px solid #FFCC80;'>
                <div style='font-size:12px; font-weight:bold; color:#E65100;'>📈 {year}년 누적</div>
                <div style='font-size:14px;'>오전 <span style='color:blue; font-weight:bold;'>{y_am}</span> / 오후 <span style='color:red; font-weight:bold;'>{y_pm}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 조(Group) 히스토리
        gh = utils.load_data("group_history")
        h_dict = {}
        if not gh.empty:
            for _, r in gh.iterrows():
                if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
                h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
            for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
            
        # ----------------------------------------------------
        # 5. 달력 그리기
        # ----------------------------------------------------
        cols = st.columns(7)
        for w in utils.WEEKDAY_KOREAN:
            cols[utils.WEEKDAY_KOREAN.index(w)].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
        
        # 리스트 출력을 위한 데이터 수집 리스트
        daily_records = []
        
        _, last_day = calendar.monthrange(year, month)
        
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, day in enumerate(week):
                with cols[i]:
                    if day == 0: 
                        st.write("")
                    else:
                        d_str = f"{year}-{month:02d}-{day:02d}"
                        weekday_str = utils.WEEKDAY_KOREAN[datetime(year, month, day).weekday()]
                        
                        grp = utils.get_group_from_dict(h_dict, target, d_str)
                        auto = utils.calculate_auto_shift(grp, d_str)
                        
                        cell_bg = "transparent"
                        txt_content = ""
                        
                        # 리스트용 변수
                        record_type = ""
                        record_detail = ""
                        
                        # 데이터 조회
                        p_work = my_work[my_work['date'] == d_str] if not my_work.empty else pd.DataFrame()
                        p_plan = my_plan[my_plan['date'] == d_str] if not my_plan.empty else pd.DataFrame()
                        
                        # [Case 1] 실제 근무 기록 존재
                        if not p_work.empty:
                            w_row = p_work.iloc[0]
                            is_sub = (str(w_row['is_sub']).upper() == 'Y' or str(w_row['is_sub']).upper() == 'TRUE')
                            
                            # 색상 결정
                            if w_row['shift'] == '오전': cell_bg = "#1e88e5" 
                            elif w_row['shift'] == '오후': cell_bg = "#e53935" 
                            if is_sub: cell_bg = "#8e24aa"

                            if w_row['shift'] == '감차휴무':
                                cell_bg = "#00592D"
                                txt_content = "<div style='line-height:1.2; color:white; font-weight:bold;'>🚫 감차<br>휴무</div>"
                                record_type = "감차휴무"
                                record_detail = "-"
                            else:
                                is_reduction = utils.is_reduction_target(d_str, w_row['route'], w_row['seq'], reduction_rules)
                                reduction_mark = ""
                                if is_reduction or '감차' in str(w_row['car']):
                                    reduction_mark = "<div style='color:#FFEB3B; font-weight:bold; font-size:10px;'>🚫 감차운행</div>"
                                
                                # [수정] HTML 코드가 깨지지 않도록 한 줄로 결합
                                txt_content = f"{reduction_mark}<div style='font-size:11px; color:white; font-weight:bold;'>{w_row['route']}노선</div><div style='font-size:11px; color:white;'>{w_row['seq']}순번</div><div style='font-size:10px; color:white; opacity:0.9;'>({w_row['car']})</div><div style='font-size:12px; font-weight:bold; color:white; margin-top:2px;'>{w_row['shift']}</div>"
                                
                                record_type = f"{w_row['shift']}" + (" (대타)" if is_sub else "")
                                record_detail = f"{w_row['route']}번 {w_row['seq']}순번 ({w_row['car']})"
                                if is_reduction: record_type += " [감차운행]"
                            
                        # [Case 2] 스케줄 신청 내역 존재
                        elif not p_plan.empty:
                            pl_row = p_plan.iloc[0]
                            t = pl_row['type']
                            note_txt = f"({pl_row['note']})" if pl_row['note'] else ""
                            
                            if t == "휴무": 
                                cell_bg = "#00592D"
                                txt_content = f"<div style='color:white; font-weight:bold;'>휴무<br><span style='font-size:10px; font-weight:normal;'>{note_txt}</span></div>"
                                record_type = "휴무(신청)"
                            else: 
                                cell_bg = utils.get_type_color(t)
                                txt_content = f"<div style='color:white; font-weight:bold;'>{t}<br><span style='font-size:10px; font-weight:normal;'>{note_txt}</span></div>"
                                record_type = t
                            record_detail = pl_row['note']
                        
                        # [Case 3] 자동 계산 (데이터 없음)
                        else:
                            if auto == "휴무":
                                cell_bg = "#f1f3f5"
                                txt_content = f"<div style='color:#999; font-weight:bold; font-size:12px;'>휴무<br>({grp})</div>"
                                record_type = "휴무(일반)"
                            elif auto == "오전": 
                                cell_bg="#e3f2fd"; txt_content=f"<div style='color:#1565C0; font-size:11px;'>오전 ({grp})</div>"
                                record_type = "오전(예정)"
                            elif auto == "오후": 
                                cell_bg="#fff3e0"; txt_content=f"<div style='color:#E65100; font-size:11px;'>오후 ({grp})</div>"
                                record_type = "오후(예정)"
                            else:
                                txt_content = "-"
                                record_type = "-"

                        # [수정] 박스 높이 고정 (height: 100px) 및 flex 정렬
                        st.markdown(f"""
                        <div style='background-color:{cell_bg}; border:1px solid #ddd; border-radius:5px; 
                                    height:100px; padding:2px; 
                                    display:flex; flex-direction:column; align-items:center; justify-content:center; 
                                    overflow:hidden;'>
                            <div style='font-weight:bold; font-size:13px; margin-bottom:2px; width:100%; text-align:center;
                                        color:{'white' if cell_bg not in ['#f1f3f5', 'transparent', '#e3f2fd', '#fff3e0'] else 'black'};'>
                                {day}
                            </div>
                            <div style='text-align:center; width:100%; line-height:1.2;'>{txt_content}</div>
                        </div>""", unsafe_allow_html=True)
                        
                        # 리스트 데이터 추가
                        daily_records.append({
                            '날짜': d_str,
                            '요일': weekday_str,
                            '근무구분': record_type,
                            '세부내용': record_detail
                        })

        # ----------------------------------------------------
        # 6. 월간 근무 이력 리스트 및 엑셀 다운로드
        # ----------------------------------------------------
        st.divider()
        st.markdown("### 📋 월간 상세 근무 이력")
        
        if daily_records:
            df_list = pd.DataFrame(daily_records)
            st.dataframe(df_list, use_container_width=True, hide_index=True)
            
            # 엑셀 다운로드 버튼
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_list.to_excel(writer, index=False, sheet_name='Sheet1')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📥 엑셀로 다운로드",
                data=processed_data,
                file_name=f"{target}_{year}년{month}월_근무이력.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("데이터가 없습니다.")
