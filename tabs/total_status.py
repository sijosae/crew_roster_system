import streamlit as st
import pandas as pd
import calendar
import concurrent.futures
from datetime import datetime, timedelta
import utils

# ==========================================
# 내부 헬퍼 함수
# ==========================================
# [변경] render_calendar_tab 전체를 @st.fragment로 감싸므로, 이 함수는 더 이상
# 별도 fragment가 아님 (Streamlit은 fragment 안에 fragment를 못 넣음)
def _render_quick_input_button(input_func):
    # (모달 대신 인라인 패널을 쓰는 이유는 input_mgr.render_quick_input_content 쪽 주석 참고)
    if 'show_quick_input' not in st.session_state:
        st.session_state['show_quick_input'] = False

    if st.button("➕ 빠른 입력", type="primary", use_container_width=True):
        st.session_state['show_quick_input'] = not st.session_state['show_quick_input']

    if st.session_state['show_quick_input']:
        # [변경] st.dialog 없이 CSS(position:fixed)만으로 모달처럼 보이게 구성.
        # 뒷배경 강제 재렌더링은 st.dialog 자체의 문제였지, "모달처럼 보이는 것"과는 무관했음.
        st.markdown("""
        <style>
        .st-key-quick_input_backdrop {
            position: fixed; inset: 0;
            background: rgba(0,0,0,0.5);
            z-index: 999;
        }
        .st-key-quick_input_panel {
            position: fixed;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 480px;
            max-height: 80vh;
            overflow-y: auto;
            z-index: 1000;
            background: white;
            box-shadow: 0 10px 40px rgba(0,0,0,0.35);
            border-radius: 10px;
            padding: 8px;
        }
        </style>
        """, unsafe_allow_html=True)
        # [변경] st.empty()로 감싸서, 저장 완료 시 전체 새로고침(st.rerun)이 일어나기 전에
        # 모달 자체를 먼저 지울 수 있게 함 (input_mgr.render_quick_input_content에서 사용)
        modal_slot = st.empty()
        with modal_slot.container():
            st.container(key="quick_input_backdrop")
            with st.container(border=True, key="quick_input_panel"):
                c_title, c_close = st.columns([5, 1])
                with c_title: st.markdown("#### ➕ 빠른 등록")
                with c_close:
                    if st.button("✕", key="quick_input_close"):
                        st.session_state['show_quick_input'] = False
                        st.rerun(scope="fragment")
                if input_func:
                    input_func(modal_slot)
                else:
                    st.warning("입력 기능 로드 실패")

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

def get_stats_optimized(date_str, drivers_list, today_schedules_records, history_dict):
    # [최적화] drivers_list/today_schedules_records는 렌더링 시작 시 한 번만 만든 일반 파이썬
    # list-of-dict임 (호출부 참고). iterrows()는 매 호출마다 pandas Series를 새로 만들어 느리므로,
    # 이 함수(달력 하루당 1회, 한 달이면 최대 31번 호출)에서는 가벼운 리스트 순회만 하도록 함.
    active_drivers_list = [dr['name'] for dr in drivers_list if not (dr['resigned_date'] and date_str > dr['resigned_date'])]

    total = len(active_drivers_list)
    am_cnt, pm_cnt, off_cnt = 0, 0, 0
    manual_map = {}
    for row in today_schedules_records:
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
# 3. 메인 렌더링 함수 (수정됨: 메모장 추가)
# ==========================================
# [최적화] 이 탭 전체를 fragment로 감싸서, 여기서 일어나는 상호작용(빠른입력 저장,
# 년월 이동 등)이 다른 5개 탭까지 다시 실행시키지 않고 이 탭만 다시 그리게 함
@st.fragment
def render_calendar_tab(input_func=None):
    if st.session_state.get('last_error_msg'):
        st.error("오류 발생")
        st.code(st.session_state['last_error_msg'])
    
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
    
    utils.inject_custom_css()
    
    now = utils.get_kst_now()
    if 'view_year' not in st.session_state: 
        st.session_state.view_year = now.year
        st.session_state.sb_view_year = now.year
    if 'view_month' not in st.session_state: 
        st.session_state.view_month = now.month
        st.session_state.sb_view_month = now.month
    
    c1, c2, c3, c4, c5, c6, c7 = st.columns([0.3, 0.7, 0.3, 0.7, 0.4, 0.4, 1.2])
    with c1: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    with c2:
        years = list(range(2023, now.year + 3))
        y_idx = years.index(st.session_state.view_year) if st.session_state.view_year in years else 0
        st.selectbox("년도", years, index=y_idx, key='sb_view_year', label_visibility="collapsed")
        if st.session_state.sb_view_year != st.session_state.view_year:
            st.session_state.view_year = st.session_state.sb_view_year; st.rerun(scope="fragment")

    with c3: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    with c4:
        months = list(range(1, 13))
        m_idx = months.index(st.session_state.view_month) if st.session_state.view_month in months else 0
        st.selectbox("월", months, index=m_idx, key='sb_view_month', label_visibility="collapsed")
        if st.session_state.sb_view_month != st.session_state.view_month:
            st.session_state.view_month = st.session_state.sb_view_month; st.rerun(scope="fragment")

    with c5: st.button("◀", key="prev_cal_btn", on_click=prev_cal_callback)
    with c6: st.button("▶", key="next_cal_btn", on_click=next_cal_callback)
    
    with c7:
        if st.session_state.get('auth_status') == 'admin':
            _render_quick_input_button(input_func)

    st.divider()
    
    year, month = st.session_state.view_year, st.session_state.view_month

    # [최적화] 서로 무관한 시트 4개를 순차적으로 기다리는 대신 동시에 요청.
    # 캐시 미스 상황(cold cache)에서는 "합산 대기시간"이 "가장 느린 것 1개" 수준으로 줄어듦
    # (스피너는 app.py에서 전체 탭을 한 번에 감싸므로 여기서는 따로 두지 않음)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _ex:
        _f_schedules = _ex.submit(utils.load_data, "schedules")
        _f_events = _ex.submit(utils.load_data, "company_events")
        _f_drivers = _ex.submit(utils.load_data, "drivers")
        _f_group_hist = _ex.submit(utils.load_data, "group_history")
        try:
            df = _f_schedules.result()
            df_events = _f_events.result()
            all_drivers = _f_drivers.result()
            group_history_df = _f_group_hist.result()
        except Exception as e:
            st.error(f"❌ 데이터 로딩 중 오류가 발생했습니다: {e}")
            st.stop()

    df_month = df[df['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df.empty else pd.DataFrame()

    full_schedule_map = {}
    if not df.empty:
        # [최적화] iterrows() 대신 zip으로 순회 (7천+행 규모라 Series 생성 비용을 피함)
        for n, d, t in zip(df['name'], df['date'].astype(str), df['type']):
            full_schedule_map[(n, d)] = t

    df_events_month = df_events[df_events['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df_events.empty else pd.DataFrame()

    # [최적화] 하루 렌더링(get_day_html)마다 반복 호출되는 get_stats_optimized가
    # DataFrame.iterrows()를 매번 새로 돌지 않도록, 여기서 딱 한 번만 일반 리스트로 변환해둠
    if not all_drivers.empty:
        if 'resigned_date' in all_drivers.columns:
            drivers_list = [
                {'name': n, 'resigned_date': str(r).strip() if r else ''}
                for n, r in zip(all_drivers['name'], all_drivers['resigned_date'])
            ]
        else:
            drivers_list = [{'name': n, 'resigned_date': ''} for n in all_drivers['name']]
    else:
        drivers_list = []

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

        today_sch_records = today_sch.to_dict('records') if not today_sch.empty else []
        full_stat, short_stat = get_stats_optimized(d_str, drivers_list, today_sch_records, history_dict)
        
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

    # [추가] 관리자 전용 메모장 (하단 배치)
    if st.session_state.get('auth_status') == 'admin':
        st.divider()
        st.subheader("🔒 관리자 전용 메모 (징계/중요사항)")
        st.info("이 내용은 DB에 저장되며, 관리자에게만 보입니다.")
        
        # 메모 로드
        current_memo = utils.get_admin_memo()
        
        # 텍스트 에디터
        new_memo = st.text_area("내용 입력", value=current_memo, height=150, key="admin_memo_area")
        
        if st.button("메모 저장", type="primary"):
            with st.spinner("저장 중..."):
                utils.save_admin_memo(new_memo)
            st.success("저장되었습니다.")
            st.rerun(scope="fragment")
