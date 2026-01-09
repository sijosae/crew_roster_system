import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
import utils

# ==========================================
# 내부 헬퍼 함수 (이 탭에서만 사용하는 로직)
# ==========================================
def prev_cal_callback():
    if st.session_state.view_month == 1:
        st.session_state.view_year -= 1
        st.session_state.view_month = 12
    else:
        st.session_state.view_month -= 1
    st.session_state.sb_view_year = st.session_state.view_year
    st.session_state.sb_view_month = st.session_state.view_month

def next_cal_callback():
    if st.session_state.view_month == 12:
        st.session_state.view_year += 1
        st.session_state.view_month = 1
    else:
        st.session_state.view_month += 1
    st.session_state.sb_view_year = st.session_state.view_year
    st.session_state.sb_view_month = st.session_state.view_month

def get_stats_optimized(date_str, all_drivers_df, today_schedules_df, history_dict):
    active_drivers_list = []
    if not all_drivers_df.empty:
        has_resign_col = 'resigned_date' in all_drivers_df.columns
        for _, dr in all_drivers_df.iterrows():
            is_active = True
            if has_resign_col:
                r_date = str(dr['resigned_date']).strip()
                if r_date and date_str > r_date: is_active = False
            if is_active: active_drivers_list.append(dr['name'])
    
    total = len(active_drivers_list)
    am_cnt, pm_cnt, off_cnt = 0, 0, 0
    manual_map = {}
    if not today_schedules_df.empty:
        for _, row in today_schedules_df.iterrows():
            manual_map[row['name']] = (row['type'], row.get('shift', '자동'))
    
    for name in active_drivers_list:
        final_shift = None
        if name in manual_map:
            typ, sft = manual_map[name]
            if typ == '휴무': final_shift = '휴무'
            elif sft and sft != '자동': final_shift = sft
        if not final_shift:
            grp = utils.get_group_from_dict(history_dict, name, date_str)
            if grp: final_shift = utils.calculate_auto_shift(grp, date_str)
        if final_shift == '오전': am_cnt += 1
        elif final_shift == '오후': pm_cnt += 1
        elif final_shift == '휴무': off_cnt += 1
            
    full_text = f"총 {total}명 (오전:{am_cnt}, 오후:{pm_cnt}, 휴무:{off_cnt})"
    short_text = f"총 {total} / 전 {am_cnt} / 후 {pm_cnt}"
    return full_text, short_text

def get_streak_info(full_schedule_map, p_name, p_date_str, p_type):
    if (p_name, p_date_str) not in full_schedule_map: return "", "", ""
    curr = datetime.strptime(p_date_str, "%Y-%m-%d")
    start_date, end_date = curr, curr
    while True:
        prev_d = (start_date - timedelta(days=1)).strftime("%Y-%m-%d")
        if (p_name, prev_d) in full_schedule_map and full_schedule_map[(p_name, prev_d)] == p_type: start_date -= timedelta(days=1)
        else: break
    while True:
        next_d = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
        if (p_name, next_d) in full_schedule_map and full_schedule_map[(p_name, next_d)] == p_type: end_date += timedelta(days=1)
        else: break
    duration = (end_date - start_date).days + 1
    prefix, suffix = "", ""
    period_text = f"(~{end_date.month}/{end_date.day})"
    if duration >= 2:
        is_start = (p_date_str == start_date.strftime("%Y-%m-%d"))
        is_end = (p_date_str == end_date.strftime("%Y-%m-%d"))
        if is_start: prefix = "➡️"; 
        if is_end: suffix = "🛑"
    return prefix, suffix, period_text

def calculate_layout_rows(df_month):
    if df_month.empty: return {}, 0
    df_sorted = df_month.sort_values(by=['name', 'date'])
    segments = []
    if not df_sorted.empty:
        curr = df_sorted.iloc[0]
        c_name, c_type, c_start, c_end = curr['name'], curr['type'], curr['date'], curr['date']
        c_recs = [curr]
        for i in range(1, len(df_sorted)):
            row = df_sorted.iloc[i]
            pd_date = datetime.strptime(c_end, "%Y-%m-%d")
            cd = datetime.strptime(row['date'], "%Y-%m-%d")
            if row['name'] == c_name and row['type'] == c_type and (cd - pd_date).days == 1:
                c_end = row['date']
                c_recs.append(row)
            else:
                segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
                c_name, c_type, c_start, c_end = row['name'], row['type'], row['date'], row['date']
                c_recs = [row]
        segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
    
    segments.sort(key=lambda x: (utils.SORT_ORDER.get(x['type'], 99), x['start'], (datetime.strptime(x['end'], "%Y-%m-%d") - datetime.strptime(x['start'], "%Y-%m-%d")).days * -1))
    lanes = {} 
    layout_map = {} 
    for seg in segments:
        seg_dates = [rec['date'] for rec in seg['records']]
        assigned_row = 0
        while True:
            is_occupied = False
            if assigned_row in lanes:
                for d in seg_dates:
                    if d in lanes[assigned_row]:
                        is_occupied = True
                        break
            if not is_occupied: break
            assigned_row += 1
        if assigned_row not in lanes: lanes[assigned_row] = set()
        lanes[assigned_row].update(seg_dates)
        recs = seg['records']
        total_len = len(recs)
        for idx, rec in enumerate(recs):
            is_start = (idx == 0)
            is_end = (idx == total_len - 1)
            layout_map[(rec['date'], assigned_row)] = { 'rec': rec, 'is_start': is_start, 'is_end': is_end, 'duration': total_len }
    max_row = max(lanes.keys()) + 1 if lanes else 0
    return layout_map, max_row

# ==========================================
# 3. 메인 렌더링 함수
# ==========================================
def render_calendar_tab():
    if st.session_state.get('last_error_msg'): 
        st.error("오류 발생")
        st.code(st.session_state['last_error_msg'])
    
    # 상단 메뉴
    c_title, c_legend, c_view = st.columns([1, 1.5, 0.8])
    with c_title:
        st.markdown("### 📅 월간 휴무 신청 현황")
    with c_legend:
        types = ["휴무", "교육", "경조사", "징계", "당일 해지", "병가", "휴직", "기타"]
        legend_html = "<div style='display:flex; flex-wrap:wrap; gap:5px; align-items:center; height:100%; margin-top:10px;'>"
        for t in types:
            c = utils.get_type_color(t)
            legend_html += f"<span style='background:{c}; color:white; border:1px solid #333; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:bold;'>{t}</span>"
        legend_html += "</div>"
        st.markdown(legend_html, unsafe_allow_html=True)
    with c_view:
        view_mode = st.radio("보기", ["가로 스크롤", "달력"], horizontal=True, label_visibility="collapsed")
    
    now = utils.get_kst_now()
    if 'view_year' not in st.session_state: st.session_state.view_year = now.year
    if 'view_month' not in st.session_state: st.session_state.view_month = now.month
    
    # 달력 이동 컨트롤
    c1, c2, c3, c4, c5, c6, c7 = st.columns([0.3, 0.7, 0.3, 0.7, 0.4, 0.4, 1.2])
    with c1: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c2: 
        years = list(range(2023, now.year + 3))
        try: y_idx = years.index(st.session_state.view_year)
        except: y_idx = 0
        st.selectbox("년도", years, index=y_idx, key='sb_view_year', label_visibility="collapsed")
        if st.session_state.sb_view_year != st.session_state.view_year:
            st.session_state.view_year = st.session_state.sb_view_year; st.rerun()

    with c3: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c4: 
        st.selectbox("월", range(1, 13), index=st.session_state.view_month-1, key='sb_view_month', label_visibility="collapsed")
        # [수정 완료] 오타 수정: view_year -> view_month로 변경하여 무한루프 해결
        if st.session_state.sb_view_month != st.session_state.view_month:
            st.session_state.view_month = st.session_state.sb_view_month; st.rerun()

    with c5: st.button("◀", key="prev_cal_btn", on_click=prev_cal_callback)
    with c6: st.button("▶", key="next_cal_btn", on_click=next_cal_callback)
    with c7:
        pass 
            
    st.divider()
    
    year, month = st.session_state.view_year, st.session_state.view_month
    
    # 데이터 로드
    df = utils.load_data("schedules")
    df_month = df[df['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df.empty else pd.DataFrame()
    
    full_schedule_map = {}
    if not df.empty:
        for _, row in df.iterrows(): full_schedule_map[(row['name'], str(row['date']))] = row['type']
        
    df_events = utils.load_data("company_events")
    df_events_month = df_events[df_events['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df_events.empty else pd.DataFrame()
    
    all_drivers = utils.load_data("drivers")
    group_history_df = utils.load_data("group_history")
    history_dict = {}
    if not group_history_df.empty:
        for _, row in group_history_df.iterrows():
            if row['driver_name'] not in history_dict: history_dict[row['driver_name']] = []
            history_dict[row['driver_name']].append((row['start_date'], row['group_name']))
        for k in history_dict: history_dict[k].sort(key=lambda x:x[0], reverse=True)
        
    _, last_day = calendar.monthrange(year, month)

    def get_day_html(day, is_horiz=True):
        d_str = f"{year}-{month:02d}-{day:02d}"
        wd_idx = datetime(year, month, day).weekday()
        
        today_sch = df_month[df_month['date'] == d_str] if not df_month.empty else pd.DataFrame()
        today_evt = df_events_month[df_events_month['date'] == d_str] if not df_events_month.empty else pd.DataFrame()
        
        full_stat, short_stat = get_stats_optimized(d_str, all_drivers, today_sch, history_dict)
        
        box_style = ""
        if d_str == now.strftime("%Y-%m-%d"):
            box_style = "box-shadow: inset 0 0 0 2px #fbc02d; background-color: #fff9c4;"
        elif d_str == (now + timedelta(days=1)).strftime("%Y-%m-%d"):
            box_style = "box-shadow: inset 0 0 0 1px #ef5350; background-color: #ffebee;"
        else:
            box_style = "background-color: white;"

        day_color = "#333"
        if wd_idx == 6 or utils.is_holiday(datetime(year, month, day)): day_color = "#d32f2f"
        elif wd_idx == 5: day_color = "#1976D2"
        
        html = f'<div class="calendar-day-box {"calendar-day-box-horiz" if is_horiz else "calendar-day-box-grid"}" style="{box_style}">'
        html += f'<div class="day-header"><div style="display:flex; justify-content:space-between; padding:0 3px;"><span style="font-weight:bold; color:{day_color};">{day}일({utils.WEEKDAY_KOREAN[wd_idx]})</span><span style="font-size:11px;">{len(today_sch)}명</span></div>'
        html += f'<div class="group-info-box">{utils.get_daily_shift_summary(d_str)}</div></div>'
        if is_horiz: html += f'<div class="daily-stats-box" title="{full_stat}">{short_stat}</div>'
        
        html += '<div class="event-container">'
        if not today_evt.empty:
            for _, e in today_evt.iterrows(): html += f"<div style='background:#E3F2FD; color:#1565C0; font-size:10px; text-align:center;'>{e['title']}</div>"
        html += '</div>'
        
        if not is_horiz and not today_sch.empty:
            today_sch['rank'] = today_sch['type'].map(lambda x: utils.SORT_ORDER.get(x, 99))
            today_sch = today_sch.sort_values(by=['rank', 'name'])
            for _, row in today_sch.iterrows():
                col = utils.get_type_color(row['type'])
                pre, suf, period_text = get_streak_info(full_schedule_map, row['name'], d_str, row['type'])
                grp = utils.get_group_from_dict(history_dict, row['name'], d_str)
                orig = utils.calculate_auto_shift(grp, d_str)
                
                orig_mk = ""
                if orig == '오전': orig_mk = "<span style='color:#87CEEB; font-weight:bold;'>(전)</span> "
                elif orig == '오후': orig_mk = "<span style='color:#FFB6C1; font-weight:bold;'>(후)</span> "
                
                inner = f"""<div style="position:relative; width:100%; display:flex; justify-content:center; align-items:center;">
                    <div style="position:absolute; left:2px;">{pre}</div>
                    <div style="width:100%; text-align:center; overflow:hidden; text-overflow:ellipsis; padding:0 14px;">{row['name']}</div>
                    <div style="position:absolute; right:2px;">{suf}</div></div>"""
                
                n_txt = row['note'] if row['note'] else row['type']
                if period_text: n_txt += f" {period_text}"
                
                sub_txt = f"<div style='font-size:9px; opacity:0.9;'>{orig_mk}{n_txt}</div>"
                html += f"<div class='schedule-bar bar-single' style='background:{col}; border:3px solid #222; color:white;' title='원래: {orig} ({grp})'>{inner}{sub_txt}</div>"
        
        html += '</div>'
        return html

    if "가로" in view_mode:
        l_map, m_row = calculate_layout_rows(df_month)
        h_html = '<div class="horizontal-scroll-container">'
        for d in range(1, last_day+1):
            d_str = f"{year}-{month:02d}-{d:02d}"
            h_html += get_day_html(d, True)[:-6]
            for r in range(m_row):
                if (d_str, r) in l_map:
                    it = l_map[(d_str, r)]
                    row = it['rec']
                    col = utils.get_type_color(row['type'])
                    pre, suf, period_text = get_streak_info(full_schedule_map, row['name'], d_str, row['type'])
                    
                    grp = utils.get_group_from_dict(history_dict, row['name'], d_str)
                    orig = utils.calculate_auto_shift(grp, d_str)
                    orig_mk = ""
                    if orig == '오전': orig_mk = "<span style='color:#87CEEB; font-weight:bold;'>(전)</span> "
                    elif orig == '오후': orig_mk = "<span style='color:#FFB6C1; font-weight:bold;'>(후)</span> "
                    
                    inner = f"""<div style="position:relative; width:100%; display:flex; justify-content:center; align-items:center;">
                        <div style="position:absolute; left:2px;">{pre}</div>
                        <div style="width:100%; text-align:center; overflow:hidden; text-overflow:ellipsis; padding:0 14px;">{row['name']}</div>
                        <div style="position:absolute; right:2px;">{suf}</div></div>"""
                    
                    n_txt = row['note'] if row['note'] else row['type']
                    if period_text: n_txt += f" {period_text}"
                    
                    sub = f"<div style='font-size:9px; opacity:0.9;'>{orig_mk}{n_txt}</div>"
                    
                    cls = "bar-single"
                    b_style = "border:3px solid #222;"
                    if it['duration'] >= 2:
                        if it['is_start']: cls = "bar-start"; b_style="border-top:3px solid #222; border-bottom:3px solid #222; border-left:3px solid #222;"
                        elif it['is_end']: cls = "bar-end"; b_style="border-top:3px solid #222; border-bottom:3px solid #222; border-right:3px solid #222;"
                        else: cls = "bar-mid"; b_style="border-top:3px solid #222; border-bottom:3px solid #222;"
                        
                    h_html += f"<div class='schedule-bar {cls}' style='background:{col}; {b_style} color:white;'>{inner}{sub}</div>"
                else: h_html += "<div class='schedule-spacer'></div>"
            h_html += "</div>"
        h_html += "</div>"
        st.markdown(h_html, unsafe_allow_html=True)
    else:
        cols = st.columns(7)
        for i, w in enumerate(utils.WEEKDAY_KOREAN): cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:{'#d32f2f' if i==6 else '#1976D2' if i==5 else 'black'};'>{w}</div>", unsafe_allow_html=True)
        for week in calendar.monthcalendar(year, month):
            cols = st.columns(7)
            for i, d in enumerate(week):
                with cols[i]:
                    if d == 0: st.markdown("<div class='calendar-day-box' style='background:#f8f9fa;'></div>", unsafe_allow_html=True)
                    else: st.markdown(get_day_html(d, False), unsafe_allow_html=True)
