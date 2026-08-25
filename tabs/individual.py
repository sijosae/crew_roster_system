import streamlit as st
import pandas as pd
import calendar
import concurrent.futures
from datetime import datetime
import io
import utils

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

def calculate_real_stats(df_work, reduction_rules, h_dict, target_name):
    cnt_am = 0
    cnt_pm = 0
    if df_work.empty: return 0, 0

    for _, row in df_work.iterrows():
        shift = row['shift']
        car = str(row['car']).strip()
        # [수정] 차량번호가 '감차'라고 적힌 게 아니면 모두 근무로 인정
        if shift == '오전' and car != '감차': cnt_am += 1
        elif shift == '오후' and car != '감차': cnt_pm += 1
        
    return cnt_am, cnt_pm

def render_individual_calendar_tab():
    st.subheader("👤 승무원별 월간 근무 현황 (통합)")
    
    st.markdown("""
    <style>
    @media (max-width: 640px) {
        .cal-content-box { font-size: 14px !important; min-height: 85px !important; padding: 5px !important; line-height: 1.4 !important; }
        .cal-header { font-size: 14px !important; margin-bottom: 5px !important; border-bottom: 1px solid #eee; padding-bottom: 2px; }
        .cal-badge { font-size: 11px !important; }
        .grp-badge { font-size: 12px; color: #666; font-weight: normal; }
    }
    </style>
    """, unsafe_allow_html=True)

    now = utils.get_kst_now()
    # [연도별 분리] work_history_{year} 시트를 읽으려면 연도를 먼저 확정해야 하므로,
    # 이 초기화 블록을 work_history 로딩보다 앞으로 옮김
    if 'indiv_view_year' not in st.session_state:
        st.session_state.indiv_view_year = now.year
        st.session_state.sb_ind_year = now.year
    if 'indiv_view_month' not in st.session_state:
        st.session_state.indiv_view_month = now.month
        st.session_state.sb_ind_month = now.month

    # [최적화] 승무원 목록만 가볍게 먼저 조회. 실제로 승무원을 선택하기 전까지는
    # schedules/work_history/group_history 같은 무거운 시트를 아예 안 불러옴
    drivers = utils.load_data("drivers")
    if drivers.empty:
        st.warning("등록된 승무원이 없습니다.")
        return

    PLACEHOLDER = "승무원을 선택하세요"
    driver_options = [PLACEHOLDER] + drivers['name'].tolist()

    c_nm, c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([2, 0.4, 0.8, 0.3, 0.7, 0.4, 0.4])

    with c_nm: target = st.selectbox("승무원 선택", driver_options, key='sel_driver', label_visibility="collapsed")
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

    if target == PLACEHOLDER:
        st.info("👆 승무원을 선택하면 근무 현황이 표시됩니다.")
        return

    # [최적화] 승무원이 실제로 선택된 경우에만 무거운 시트 4개를 병렬로 조회
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _ex:
        _f_schedules = _ex.submit(utils.load_data, "schedules")
        _f_work = _ex.submit(utils.load_work_history_for_year, st.session_state.indiv_view_year)
        _f_group_hist = _ex.submit(utils.load_data, "group_history")
        _f_reduction = _ex.submit(utils.get_reduction_rules)
        try:
            df_plan = _f_schedules.result()
            df_work = _f_work.result()
            gh_df = _f_group_hist.result()
            reduction_rules = _f_reduction.result()
        except Exception as e:
            st.error(f"❌ 데이터 로딩 중 오류가 발생했습니다: {e}")
            st.stop()

    h_dict = {}
    if not gh_df.empty:
        for _, r in gh_df.iterrows():
            if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
            h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
        for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)

    if df_work.empty:
        df_work = pd.DataFrame(columns=['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub'])
    else:
        required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub']
        for c in required_cols:
            if c not in df_work.columns: df_work[c] = ""

    if target:
        year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
        filter_ym = f"{year}-{month:02d}"
        
        if not gh_df.empty:
            my_history = gh_df[gh_df['driver_name'] == target].sort_values(by='start_date', ascending=False)
            if not my_history.empty:
                current_grp = my_history.iloc[0]['group_name']
                with st.expander(f"📜 {target}님 소속 조 이력 (현재: {current_grp})", expanded=False):
                    st.dataframe(my_history[['start_date', 'group_name']], hide_index=True, use_container_width=True)
        
        my_plan = df_plan[(df_plan['name']==target) & (df_plan['date'].astype(str).str.startswith(filter_ym))] if not df_plan.empty else pd.DataFrame()
        my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))] if not df_work.empty else pd.DataFrame()
        
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
                    if day == 0: st.write("")
                    else:
                        d_str = f"{year}-{month:02d}-{day:02d}"
                        weekday_str = utils.WEEKDAY_KOREAN[datetime(year, month, day).weekday()]
                        
                        grp = utils.get_group_from_dict(h_dict, target, d_str)
                        auto = utils.calculate_auto_shift(grp, d_str)
                        grp_txt = f"({grp})" if grp else ""
                        
                        cell_bg = "transparent"
                        txt_content = ""
                        border_style = "border:1px solid #ddd;"
                        
                        p_work = my_work[my_work['date'] == d_str] if not my_work.empty else pd.DataFrame()
                        p_plan = my_plan[my_plan['date'] == d_str] if not my_plan.empty else pd.DataFrame()
                        
                        rec_shift, rec_route, rec_seq, rec_car = "", "-", "-", "-"

                        # [Case 1] 실제 근무 기록 존재
                        if not p_work.empty:
                            w_row = p_work.iloc[0]
                            is_sub = (str(w_row['is_sub']).upper() in ['Y', 'TRUE'])
                            
                            # 차량번호가 '감차'라고 적힌 경우만 휴무 처리
                            if str(w_row['car']).strip() == "감차":
                                cell_bg = "#00592D"
                                txt_content = f"<div style='width:100%; text-align:center;'><div class='cal-badge' style='color:#ff4444; font-weight:bold; font-size:11px;'>🚫 감차휴무</div><div style='color:white; font-weight:bold; font-size:13px;'>휴무 {grp_txt}</div></div>"
                                rec_shift = "휴무(감차)"
                            else:
                                # [핵심] 실제 근무 시 감차 여부 상관없이 근무 표시
                                if w_row['shift'] == '오전': cell_bg = "#1e88e5"
                                else: cell_bg = "#e53935"
                                
                                if is_sub:
                                    if w_row['shift'] == '오전': cell_bg = "#1565C0"
                                    else: cell_bg = "#EF6C00"
                                
                                sub_txt = "<span style='color:#FFEB3B; font-weight:bold;'>(대운)</span>" if is_sub else ""
                                
                                txt_content = f"<div style='width:100%; text-align:center; color:white;'><div style='font-size:14px; font-weight:bold;'>{w_row['route']}노선 {w_row['seq']}순번</div><div style='font-size:13px;'>{w_row['car']}</div><div style='font-size:14px; font-weight:bold; margin-top:2px;'>{w_row['shift']} {sub_txt} <span style='font-size:11px; font-weight:normal;'>{grp_txt}</span></div></div>"
                                
                                rec_shift = f"{w_row['shift']}" + (" (대운)" if is_sub else "")
                                rec_route = w_row['route']
                                rec_seq = w_row['seq']
                                rec_car = w_row['car']

                        # [Case 2] 계획(스케줄)만 있는 경우
                        elif not p_plan.empty:
                            pl_row = p_plan.iloc[0]
                            t = pl_row['type']
                            if t in ['휴무', '감차휴무']:
                                cell_bg = "#00592D"
                                txt_content = f"<div style='width:100%; text-align:center;'><div style='color:white; font-weight:bold; font-size:13px;'>휴무 {grp_txt}</div></div>"
                                rec_shift = "휴무(신청)"
                            else:
                                cell_bg = utils.get_type_color(t)
                                txt_content = f"<div style='color:white; font-weight:bold; font-size:13px;'>{t} {grp_txt}</div>"
                                rec_shift = t
                        
                        # [Case 3] 자동 스케줄
                        else:
                            if auto == "휴무":
                                cell_bg = "#f1f3f5"
                                txt_content = f"<div style='color:#999; font-weight:bold; font-size:13px;'>휴무<br>{grp_txt}</div>"
                                rec_shift = "휴무(일반)"
                            elif auto == "오전": 
                                cell_bg="#e3f2fd"; txt_content=f"<div style='color:blue; font-size:13px;'>오전 {grp_txt}</div>"
                                rec_shift = "오전(예정)"
                            elif auto == "오후": 
                                cell_bg="#fff3e0"; txt_content=f"<div style='color:red; font-size:13px;'>오후 {grp_txt}</div>"
                                rec_shift = "오후(예정)"
                            else:
                                txt_content = "-"
                                rec_shift = "-"

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
                        
                        daily_records.append({
                            '날짜': d_str, '요일': weekday_str, '조': grp,
                            '근무구분': rec_shift, '노선': rec_route, '순번': rec_seq, '차량번호': rec_car
                        })

        st.divider()
        st.markdown("### 📋 월간 상세 근무 이력")
        if daily_records:
            df_list = pd.DataFrame(daily_records)
            st.dataframe(df_list, use_container_width=True, hide_index=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_list.to_excel(writer, index=False, sheet_name='Sheet1')
            st.download_button("📥 엑셀로 다운로드", output.getvalue(), f"{target}_{year}년{month}월.xlsx")
