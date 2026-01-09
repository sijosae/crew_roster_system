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
# 2. 통계 계산 함수
# ==========================================
def calculate_real_stats(df_work, reduction_rules, h_dict, target_name):
    cnt_am = 0
    cnt_pm = 0
    if df_work.empty: return 0, 0

    for _, row in df_work.iterrows():
        shift = row['shift']
        if shift not in ['오전', '오후']: continue
        d_str = row['date']
        
        # 감차 여부 확인
        is_red = utils.is_reduction_target(d_str, row['route'], row['seq'], reduction_rules)
        # 대운(대타) 여부 확인
        is_sub = (str(row['is_sub']).upper() in ['Y', 'TRUE'])
        # 차량명에 '감차' 포함 여부
        car_is_red = '감차' in str(row['car'])
        
        # [제외 조건] 감차 대상(규칙 or 차량명)이고 대운(대타)이 아니면 -> 근무 횟수에서 제외 (휴무로 간주)
        if (is_red or car_is_red) and not is_sub:
            continue
            
        if shift == '오전': cnt_am += 1
        elif shift == '오후': cnt_pm += 1
        
    return cnt_am, cnt_pm

# ==========================================
# 3. 메인 렌더링 함수
# ==========================================
def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황 (통합)")
    
    # [CSS 수정] 모바일 가로 고정 (PC 영향 없음)
    st.markdown("""
    <style>
    @media (max-width: 640px) {
        /* 모바일에서 컬럼 강제 가로 정렬 */
        div[data-testid="column"] {
            width: 14.28% !important;
            flex: 0 0 14.28% !important;
            min-width: 0px !important;
            padding: 1px !important;
        }
        /* 모바일 폰트 및 박스 크기 조정 */
        .cal-content-box {
            font-size: 9px !important;
            min-height: 55px !important;
            padding: 1px !important;
            line-height: 1.1 !important;
        }
        .cal-header {
            font-size: 10px !important;
            margin-bottom: 1px !important;
        }
        /* 감차/대운 등 뱃지 폰트 축소 */
        .cal-badge {
            font-size: 8px !important;
        }
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
    
    # 조 히스토리 로드
    gh = utils.load_data("group_history")
    h_dict = {}
    if not gh.empty:
        for _, r in gh.iterrows():
            if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
            h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
        for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
    
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

    # 4. 달력 렌더링
    if target:
        year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
        filter_ym = f"{year}-{month:02d}"
        
        my_plan = df_plan[(df_plan['name']==target) & (df_plan['date'].astype(str).str.startswith(filter_ym))] if not df_plan.empty else pd.DataFrame()
        my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))] if not df_work.empty else pd.DataFrame()
        
        # 통계 계산
        stats_am, stats_pm = calculate_real_stats(my_work, reduction_rules, h_dict, target)
        
        y_filter = f"{year}-"
        y_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(y_filter))] if not df_work.empty else pd.DataFrame()
        y_am, y_pm = calculate_real_stats(y_work, reduction_rules, h_dict, target)
        
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
            
        cols = st.columns(7)
        for w in utils.WEEKDAY_KOREAN:
            cols[utils.WEEKDAY_KOREAN.index(w)].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
        
        daily_records = []
        
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
                        border_style = "border:1px solid #ddd;"
                        
                        rec_shift = ""
                        rec_route = "-"
                        rec_seq = "-"
                        rec_car = "-"
                        
                        p_work = my_work[my_work['date'] == d_str] if not my_work.empty else pd.DataFrame()
                        p_plan = my_plan[my_plan['date'] == d_str] if not my_plan.empty else pd.DataFrame()
                        
                        # [Case 1] 근무 이력(DB) 존재
                        if not p_work.empty:
                            w_row = p_work.iloc[0]
                            # 대운(대타) 여부 확인
                            is_sub = (str(w_row['is_sub']).upper() in ['Y', 'TRUE'])
                            
                            # 감차 확인
                            is_rule_red = utils.is_reduction_target(d_str, w_row['route'], w_row['seq'], reduction_rules)
                            is_car_red = '감차' in str(w_row['car'])
                            is_reduction = is_rule_red or is_car_red

                            # [1] 감차 대상이고 + 대운(대타)이 아니다? => 무조건 휴무 처리
                            if is_reduction and not is_sub:
                                if auto == '휴무':
                                    cell_bg = "#f1f3f5"
                                    txt_content = f"<div style='width:100%; text-align:center;'><div class='cal-badge' style='color:#ff4444; font-weight:bold; font-size:11px;'>🚫 감차</div><div style='color:#999; font-weight:bold; font-size:13px;'>휴무<br>({grp})</div></div>"
                                    rec_shift = "휴무(감차/원래휴무)"
                                else:
                                    cell_bg = "#00592D"
                                    txt_content = f"<div style='width:100%; text-align:center;'><div class='cal-badge' style='color:#ff4444; font-weight:bold; font-size:11px;'>🚫 감차</div><div style='color:white; font-weight:bold; font-size:13px;'>휴무</div></div>"
                                    rec_shift = "휴무(감차)"
                            
                            # [2] 명시적 감차휴무
                            elif w_row['shift'] == '감차휴무':
                                cell_bg = "#00592D"
                                txt_content = f"<div style='width:100%; text-align:center;'><div class='cal-badge' style='color:#ff4444; font-weight:bold; font-size:11px;'>🚫 감차</div><div style='color:white; font-weight:bold; font-size:13px;'>휴무</div></div>"
                                rec_shift = "휴무(감차)"
                            
                            # [3] 실제 근무 (오전/오후)
                            elif w_row['shift'] in ['오전', '오후']:
                                # [수정] 대운(대타) 색상 로직 변경
                                if is_sub:
                                    border_style = "border:3px solid #8e24aa;" # 보라색 테두리
                                    if w_row['shift'] == '오전': 
                                        cell_bg = "#1565C0" # 대운 오전 (진한 남색/파랑)
                                    else: 
                                        cell_bg = "#EF6C00" # 대운 오후 (주황색)
                                else:
                                    # 일반 근무
                                    if w_row['shift'] == '오전': cell_bg = "#1e88e5" 
                                    else: cell_bg = "#e53935" 
                                
                                mark = ""
                                # 감차 대상인데 근무 (규칙상 감차) -> 빨간색 경고
                                if is_rule_red: 
                                    mark += "<div class='cal-badge' style='color:#ff4444; font-weight:bold; font-size:11px;'>🚫 감차근무</div>"
                                
                                # 대운 문구 추가
                                sub_txt = ""
                                if is_sub:
                                    sub_txt = "<span style='color:#FFEB3B; font-weight:bold;'>(대운)</span>"

                                car_text = f"{w_row['car']}"
                                shift_txt = f"{w_row['shift']} {sub_txt}"
                                
                                txt_content = f"<div style='width:100%; text-align:center; color:white;'>{mark}<div style='font-size:14px; font-weight:bold;'>{w_row['route']}노선 {w_row['seq']}순번</div><div style='font-size:13px;'>{car_text}</div><div style='font-size:14px; font-weight:bold; margin-top:2px;'>{shift_txt}</div></div>"
                                
                                rec_shift = f"{w_row['shift']}" + (" (대운)" if is_sub else "")
                                rec_route = w_row['route']
                                rec_seq = w_row['seq']
                                rec_car = w_row['car']
                                
                            else:
                                cell_bg = "#00592D"
                                txt_content = f"<div style='color:white; font-size:13px; font-weight:bold;'>{w_row['shift']}</div>"
                                rec_shift = w_row['shift']

                        # [Case 2] 스케줄 신청
                        elif not p_plan.empty:
                            pl_row = p_plan.iloc[0]
                            t = pl_row['type']
                            
                            if t in ['휴무', '감차휴무']:
                                if auto == '휴무': 
                                    cell_bg = "#f1f3f5"
                                    txt_content = f"<div style='color:#999; font-weight:bold; font-size:13px;'>휴무<br>({grp})</div>"
                                    rec_shift = "휴무(원래휴무)"
                                else:
                                    cell_bg = "#00592D"
                                    # [수정] 빨간색 감차 표시
                                    mark = "<div class='cal-badge' style='color:#ff4444; font-size:11px; font-weight:bold;'>🚫 감차</div>" if t == '감차휴무' else ""
                                    txt_content = f"<div style='width:100%; text-align:center;'>{mark}<div style='color:white; font-weight:bold; font-size:13px;'>휴무</div></div>"
                                    rec_shift = "휴무(신청)"
                            else:
                                cell_bg = utils.get_type_color(t)
                                txt_content = f"<div style='color:white; font-weight:bold; font-size:13px;'>{t}</div>"
                                rec_shift = t
                            
                            if pl_row['note']: rec_route = pl_row['note']
                        
                        # [Case 3] 데이터 없음
                        else:
                            if auto == "휴무":
                                cell_bg = "#f1f3f5"
                                txt_content = f"<div style='color:#999; font-weight:bold; font-size:13px;'>휴무<br>({grp})</div>"
                                rec_shift = "휴무(일반)"
                            elif auto == "오전": 
                                cell_bg="#e3f2fd"; 
                                txt_content=f"<div style='color:blue; font-size:13px;'>오전 ({grp})</div>"
                                rec_shift = "오전(예정)"
                            elif auto == "오후": 
                                cell_bg="#fff3e0"; 
                                txt_content=f"<div style='color:red; font-size:13px;'>오후 ({grp})</div>"
                                rec_shift = "오후(예정)"
                            else:
                                txt_content = "-"
                                rec_shift = "-"
                            
                            rec_route, rec_seq, rec_car = "-", "-", "-"

                        st.markdown(f"""
                        <div class='cal-content-box' style='background-color:{cell_bg}; {border_style} border-radius:5px; 
                                    min-height:100px; height:auto; padding:5px; 
                                    display:flex; flex-direction:column; align-items:center; justify-content:center; 
                                    overflow:hidden; word-break:keep-all;'>
                            <div class='cal-header' style='font-weight:bold; font-size:13px; margin-bottom:4px; width:100%; text-align:center;
                                        color:{'white' if cell_bg not in ['#f1f3f5', 'transparent', '#e3f2fd', '#fff3e0'] else 'black'};'>
                                {day}
                            </div>
                            {txt_content}
                        </div>""", unsafe_allow_html=True)
                        
                        weekday_str = utils.WEEKDAY_KOREAN[datetime(year, month, day).weekday()]
                        daily_records.append({
                            '날짜': d_str,
                            '요일': weekday_str,
                            '근무구분': rec_shift,
                            '노선': rec_route,
                            '순번': rec_seq,
                            '차량번호': rec_car
                        })

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
