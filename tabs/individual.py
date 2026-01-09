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
    
    # [CSS] 모바일 강제 캘린더 그리드 스타일 주입
    st.markdown("""
    <style>
        .custom-cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; width: 100%; margin-bottom: 20px; }
        .cal-header-cell { text-align: center; font-weight: bold; padding: 5px 0; background-color: white; border-bottom: 2px solid #eee; font-size: 14px; }
        .cal-cell { border: 1px solid #e9ecef; border-radius: 4px; min-height: 100px; padding: 2px; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden; word-break: keep-all; }
        @media (max-width: 640px) {
            .cal-header-cell { font-size: 12px; }
            .cal-cell { min-height: 80px; font-size: 11px; }
            .cell-date { font-size: 11px !important; }
            .cell-content { font-size: 10px !important; }
        }
    </style>
    """, unsafe_allow_html=True)
    
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
        st.session_state.sb_ind_year = now.year
    if 'indiv_view_month' not in st.session_state: 
        st.session_state.indiv_view_month = now.month
        st.session_state.sb_ind_month = now.month
    
    # 3. 컨트롤 패널
    c_nm, c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([2, 0.4, 0.8, 0.3, 0.7, 0.4, 0.4])
    
    with c_nm: 
        target = st.selectbox("승무원 선택", drivers['name'].tolist(), key='sel_driver', label_visibility="collapsed")
    with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c_yr: 
        year_range = range(2023, now.year + 3)
        selected_year = st.selectbox("년도", year_range, key='sb_ind_year', label_visibility="collapsed")
        if selected_year != st.session_state.indiv_view_year:
            st.session_state.indiv_view_year = selected_year
            st.rerun()
    with c_mo_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c_mo: 
        month_range = range(1, 13)
        selected_month = st.selectbox("월", month_range, key='sb_ind_month', label_visibility="collapsed")
        if selected_month != st.session_state.indiv_view_month:
            st.session_state.indiv_view_month = selected_month
            st.rerun()
    with c_prev: st.button("◀", key="i_prev_btn", on_click=prev_month_indiv)
    with c_next: st.button("▶", key="i_next_btn", on_click=next_month_indiv)
    
    st.divider()

    if target:
        year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
        filter_ym = f"{year}-{month:02d}"
        
        my_plan = df_plan[(df_plan['name']==target) & (df_plan['date'].astype(str).str.startswith(filter_ym))] if not df_plan.empty else pd.DataFrame()
        my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))] if not df_work.empty else pd.DataFrame()
        
        # 통계 (근무만)
        stats_am = len(my_work[my_work['shift'] == '오전']) if not my_work.empty else 0
        stats_pm = len(my_work[my_work['shift'] == '오후']) if not my_work.empty else 0
        
        y_filter = f"{year}-"
        y_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(y_filter))] if not df_work.empty else pd.DataFrame()
        y_am = len(y_work[y_work['shift'] == '오전']) if not y_work.empty else 0
        y_pm = len(y_work[y_work['shift'] == '오후']) if not y_work.empty else 0
        
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
        
        gh = utils.load_data("group_history")
        h_dict = {}
        if not gh.empty:
            for _, r in gh.iterrows():
                if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
                h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
            for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
        
        # -----------------------------------------------
        # [모바일 대응] CSS Grid 캘린더 생성
        # -----------------------------------------------
        cal_html = '<div class="custom-cal-grid">'
        for w in utils.WEEKDAY_KOREAN:
            cal_html += f'<div class="cal-header-cell">{w}</div>'
            
        daily_records = []
        
        for week in calendar.monthcalendar(year, month):
            for day in week:
                if day == 0: 
                    cal_html += '<div class="cal-cell" style="background-color:#f8f9fa;"></div>'
                    continue

                d_str = f"{year}-{month:02d}-{day:02d}"
                weekday_str = utils.WEEKDAY_KOREAN[datetime(year, month, day).weekday()]
                
                grp = utils.get_group_from_dict(h_dict, target, d_str)
                auto = utils.calculate_auto_shift(grp, d_str)
                
                cell_bg = "transparent"
                txt_content = ""
                date_color = "black"
                
                rec_shift = ""
                rec_route = ""
                rec_seq = ""
                rec_car = ""
                
                p_work = my_work[my_work['date'] == d_str] if not my_work.empty else pd.DataFrame()
                p_plan = my_plan[my_plan['date'] == d_str] if not my_plan.empty else pd.DataFrame()
                
                # [Case 1] 근무 이력(DB) 존재
                if not p_work.empty:
                    w_row = p_work.iloc[0]
                    is_sub = (str(w_row['is_sub']).upper() == 'Y' or str(w_row['is_sub']).upper() == 'TRUE')
                    is_reduction = utils.is_reduction_target(d_str, w_row['route'], w_row['seq'], reduction_rules)

                    # [우선순위 1] (원래 휴무일) AND (감차 대상) AND (대타 아님)
                    # -> 배경은 회색(일반휴무), 텍스트는 감차/조휴무 정보 유지 (글자색 진하게)
                    if auto == '휴무' and is_reduction and not is_sub:
                        cell_bg = "#f1f3f5" # 회색 배경
                        txt_content = f"<div style='line-height:1.2; font-weight:bold; font-size:13px;'><span style='color:#d32f2f;'>🚫 감차휴무</span><br><span style='color:#999; font-size:11px; font-weight:normal;'>({grp} 휴무)</span></div>"
                        rec_shift = f"감차휴무({grp})"
                        rec_route, rec_seq, rec_car = "-", "-", "-"

                    # [우선순위 2] 감차휴무 명시 -> 녹색
                    elif w_row['shift'] == '감차휴무':
                        cell_bg = "#00592D"
                        txt_content = "<div style='line-height:1.2; color:white; font-weight:bold; font-size:14px;'>🚫 감차<br>휴무</div>"
                        rec_shift = "감차휴무"
                        rec_route, rec_seq, rec_car = "-", "-", "-"

                    # [우선순위 3] 근무 기록 (오전/오후)
                    elif w_row['shift'] in ['오전', '오후']:
                        # 감차 대상인데 차는 쉼 (대타 아님) -> 감차휴무 (녹색)
                        if is_reduction and not is_sub:
                            cell_bg = "#00592D"
                            txt_content = "<div style='line-height:1.2; color:white; font-weight:bold; font-size:14px;'>🚫 감차<br>휴무</div>"
                            rec_shift = "감차휴무"
                            rec_route, rec_seq, rec_car = "-", "-", "-"
                        
                        # 진짜 근무
                        else:
                            # 색상 구분 (일반/대타)
                            if is_sub:
                                if w_row['shift'] == '오전': cell_bg = "#303F9F"  # Dark Indigo
                                elif w_row['shift'] == '오후': cell_bg = "#C2185B"  # Dark Pink
                            else:
                                if w_row['shift'] == '오전': cell_bg = "#1e88e5" 
                                elif w_row['shift'] == '오후': cell_bg = "#e53935" 
                            
                            # 감차차량 근무 표시
                            mark = ""
                            if is_reduction or '감차' in str(w_row['car']):
                                mark = "<div style='color:#FFEB3B; font-weight:bold; font-size:11px;'>🚫 감차</div>"
                            
                            car_text = f"{w_row['car']}"
                            rec_shift = f"{w_row['shift']}"
                            if is_sub: rec_shift += " (대타)"
                            
                            txt_content = f"<div style='line-height:1.4; color:white;'>{mark}<div style='font-size:14px; font-weight:bold;'>{w_row['route']}노선 {w_row['seq']}순번</div><div style='font-size:13px;'>{car_text}</div><div style='font-size:14px; font-weight:bold; margin-top:2px;'>{w_row['shift']}</div></div>"
                            rec_route, rec_seq, rec_car = w_row['route'], w_row['seq'], w_row['car']
                    else:
                        cell_bg = "#00592D"
                        txt_content = f"<div style='color:white; font-size:14px; font-weight:bold;'>{w_row['shift']}</div>"
                        rec_shift = w_row['shift']
                        rec_route, rec_seq, rec_car = "-", "-", "-"
                    
                # [Case 2] 스케줄 신청 내역
                elif not p_plan.empty:
                    pl_row = p_plan.iloc[0]
                    t = pl_row['type']
                    note_txt = f"<br><span style='font-size:11px; font-weight:normal;'>({pl_row['note']})</span>" if pl_row['note'] else ""
                    
                    if auto == '휴무' and (t == '휴무' or t == '감차휴무'):
                        cell_bg = "#f1f3f5"
                        txt_content = f"<div style='color:#999; font-weight:bold; font-size:13px;'>휴무<br>({grp})</div>"
                        rec_shift = "휴무(원래휴무)"
                    elif t == '감차휴무':
                        cell_bg = "#00592D"
                        txt_content = "<div style='line-height:1.2; color:white; font-weight:bold; font-size:14px;'>🚫 감차<br>휴무</div>"
                        rec_shift = "감차휴무"
                    elif t == "휴무": 
                        cell_bg = "#00592D"
                        txt_content = f"<div style='color:white; font-size:14px; font-weight:bold;'>휴무{note_txt}</div>"
                        rec_shift = "휴무(신청)"
                    else: 
                        cell_bg = utils.get_type_color(t)
                        txt_content = f"<div style='color:white; font-size:14px; font-weight:bold;'>{t}{note_txt}</div>"
                        rec_shift = t
                    
                    rec_route = pl_row['note']
                    rec_seq, rec_car = "-", "-"
                
                # [Case 3] 데이터 없음
                else:
                    if auto == "휴무":
                        cell_bg = "#f1f3f5"
                        txt_content = f"<div style='color:#999; font-weight:bold; font-size:13px;'>휴무<br>({grp})</div>"
                        rec_shift = "휴무(일반)"
                    elif auto == "오전": 
                        cell_bg="#e3f2fd"; txt_content=f"<div style='color:blue; font-size:13px;'>오전 ({grp})</div>"
                        rec_shift = "오전(예정)"
                    elif auto == "오후": 
                        cell_bg="#fff3e0"; txt_content=f"<div style='color:red; font-size:13px;'>오후 ({grp})</div>"
                        rec_shift = "오후(예정)"
                    else:
                        txt_content = "-"
                        rec_shift = "-"
                    
                    rec_route, rec_seq, rec_car = "-", "-", "-"
                
                # 날짜 색상 처리
                if cell_bg in ['#f1f3f5', 'transparent', '#e3f2fd', '#fff3e0']:
                    date_color = "black"
                else:
                    date_color = "white"

                cal_html += f"""
                <div class="cal-cell" style="background-color:{cell_bg};">
                    <div class="cell-date" style="font-weight:bold; font-size:13px; margin-bottom:4px; color:{date_color};">{day}</div>
                    <div class="cell-content" style="text-align:center; width:100%;">{txt_content}</div>
                </div>
                """
                
                daily_records.append({
                    '날짜': d_str,
                    '요일': weekday_str,
                    '근무구분': rec_shift,
                    '노선': rec_route,
                    '순번': rec_seq,
                    '차량번호': rec_car
                })

        cal_html += '</div>'
        st.markdown(cal_html, unsafe_allow_html=True)

        st.divider()
        st.markdown("### 📋 월간 상세 근무 이력")
        
        if daily_records:
            df_list = pd.DataFrame(daily_records)
            st.dataframe(
                df_list, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "날짜": st.column_config.TextColumn("날짜", width="small"),
                    "요일": st.column_config.TextColumn("요일", width="small"),
                    "근무구분": st.column_config.TextColumn("근무구분", width="medium"),
                    "노선": st.column_config.TextColumn("노선", width="small"),
                    "순번": st.column_config.TextColumn("순번", width="small"),
                    "차량번호": st.column_config.TextColumn("차량번호", width="small"),
                }
            )
            
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
