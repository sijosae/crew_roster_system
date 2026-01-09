import streamlit as st
import pandas as pd
from datetime import datetime
import re
import time
import traceback
import utils

# ==========================================
# 내부 데이터 처리 함수
# ==========================================
def save_range_batch(name_list, start, end, type, shift, note):
    dates = pd.date_range(start, end)
    now_kst = utils.get_kst_now()
    created_at = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    base_id = now_kst.strftime("%y%m%d%H%M") 
    
    rows_to_add = []
    generated_ids = [] 
    count = 0
    for name in name_list:
        for d in dates:
            d_str = d.strftime("%Y-%m-%d")
            row_id = f"{base_id}{count:02d}"
            generated_ids.append(row_id)
            rows_to_add.append([row_id, name, d_str, type, note, created_at, shift])
            count += 1
            
    if rows_to_add:
        sh = utils.get_db_connection()
        ws = sh.worksheet("schedules")
        ws.append_rows(rows_to_add)
        utils.clear_cache_after_save()
        
    return len(rows_to_add), generated_ids

def parse_roster_excel(file):
    df_raw = pd.read_excel(file, header=None)
    date_rows = []
    for idx, row in df_raw.iterrows():
        val = str(row[0])
        if "202" in val or "년" in val:
            try:
                if pd.notnull(df_raw.iloc[idx, 3]) and pd.notnull(df_raw.iloc[idx, 5]):
                    date_rows.append(idx)
            except: pass
            
    extracted_data = [] 
    
    for start_row in date_rows:
        try:
            year = int(str(df_raw.iloc[start_row, 0]).replace("년","").strip())
            month = int(str(df_raw.iloc[start_row, 3]).replace("월","").strip())
            day = int(str(df_raw.iloc[start_row, 5]).replace("일","").strip())
            current_date = datetime(year, month, day).strftime("%Y-%m-%d")
        except: continue 

        cols_map = [
            {'route':1, 'seq':2, 'car':3, 'am_fix':4, 'am_sub':5, 'pm_fix':6, 'pm_sub':7}, # Left
            {'route':9, 'seq':10, 'car':11, 'am_fix':12, 'am_sub':13, 'pm_fix':14, 'pm_sub':15} # Right
        ]
        
        for side in cols_map:
            last_route = None
            for r_offset in range(3, 75): 
                curr_idx = start_row + r_offset
                if curr_idx >= len(df_raw): break
                
                raw_route = df_raw.iloc[curr_idx, side['route']]
                if pd.notnull(raw_route) and str(raw_route).strip() != "":
                    last_route = str(raw_route).strip()
                current_route = last_route if last_route else ""

                raw_seq = df_raw.iloc[curr_idx, side['seq']]
                raw_car = df_raw.iloc[curr_idx, side['car']]
                
                current_seq = str(raw_seq).strip() if pd.notnull(raw_seq) else ""
                
                try:
                    raw_car_str = str(raw_car).strip()
                    digits_only = re.sub(r'[^0-9]', '', raw_car_str)
                    car_num = int(digits_only)
                    is_valid_car = (5001 <= car_num <= 5300)
                    current_car = str(car_num)
                except:
                    is_valid_car = False
                    current_car = ""

                if not (current_route and current_seq and is_valid_car):
                    continue
                
                am_fix = utils.clean_driver_name(df_raw.iloc[curr_idx, side['am_fix']])
                am_sub = utils.clean_driver_name(df_raw.iloc[curr_idx, side['am_sub']])
                am_final = am_sub if am_sub else am_fix
                
                pm_fix = utils.clean_driver_name(df_raw.iloc[curr_idx, side['pm_fix']])
                pm_sub = utils.clean_driver_name(df_raw.iloc[curr_idx, side['pm_sub']])
                pm_final = pm_sub if pm_sub else pm_fix
                
                if am_final: 
                    extracted_data.append({
                        'date': current_date, 'name': am_final, 'shift': '오전', 
                        'route': current_route, 'seq': current_seq, 'car': current_car, 
                        'is_sub': bool(am_sub), 'orig_fix': am_fix
                    })
                
                if pm_final:
                    extracted_data.append({
                        'date': current_date, 'name': pm_final, 'shift': '오후', 
                        'route': current_route, 'seq': current_seq, 'car': current_car, 
                        'is_sub': bool(pm_sub), 'orig_fix': pm_fix
                    })
    return pd.DataFrame(extracted_data)

def save_work_history(df_new):
    sh = utils.get_db_connection()
    try:
        ws = sh.worksheet("work_history")
    except:
        ws = sh.add_worksheet(title="work_history", rows=1000, cols=10)
        ws.append_row(['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at'])

    existing_data = ws.get_all_values()
    df_old = pd.DataFrame()
    if len(existing_data) > 1:
        headers = existing_data.pop(0)
        df_old = pd.DataFrame(existing_data, columns=headers)
    
    if df_old.empty:
        df_final = df_new
    else:
        required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at']
        for c in required_cols:
            if c not in df_new.columns: df_new[c] = ""
            if c not in df_old.columns: df_old[c] = ""
        df_new = df_new[required_cols]
        df_old = df_old[required_cols]
        
        df_combined = pd.concat([df_old, df_new])
        actually_worked = df_combined[df_combined['shift'] != '감차휴무'][['date', 'name']].drop_duplicates()
        actually_worked['worked_flag'] = True
        df_merged = pd.merge(df_combined, actually_worked, on=['date', 'name'], how='left')
        df_final = df_merged[~((df_merged['worked_flag'] == True) & (df_merged['shift'] == '감차휴무'))]
        if 'worked_flag' in df_final.columns: df_final = df_final.drop(columns=['worked_flag'])
        df_final = df_final.drop_duplicates(subset=['date', 'name', 'shift'], keep='last')
        
    df_final = df_final.sort_values(by=['date', 'name'])
    ws.clear()
    ws.append_row(['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at'])
    data_to_write = df_final.fillna("").astype(str).values.tolist()
    if data_to_write: ws.append_rows(data_to_write)
    utils.clear_cache_after_save()
    return len(df_new)

def add_reduction_rule(start, end, route, seq, cond):
    sh = utils.get_db_connection()
    try: ws = sh.worksheet("reduction_rules")
    except:
        ws = sh.add_worksheet(title="reduction_rules", rows=100, cols=5)
        ws.append_row(['start_date', 'end_date', 'route', 'sequence', 'condition'])
    ws.append_row([str(start), str(end), str(route), str(seq), cond])
    utils.clear_cache_after_save()

# ==========================================
# 메인 렌더링
# ==========================================
def render_input_tab():
    st.subheader("📝 관리자 입력 & 배차 관리")
    t1, t2, t3, t4 = st.tabs(["휴무 등록", "행사 등록", "📂 배차일지 업로드", "⚙️ 감차 규칙"])
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
                    with st.spinner('저장...'): save_range_batch([n.strip() for n in names_str.split('\n') if n.strip()], rng[0], rng[-1], typ, sft, nte)
                    st.success("완료"); st.rerun()
                except: st.error("오류")
    with t2:
        ed = st.date_input("행사 기간", [], key="evt_rng")
        et = st.text_input("내용", key="evt_tit")
        if st.button("행사 저장"):
            if et and len(ed) > 0:
                for d in pd.date_range(ed[0], ed[-1]): utils.add_company_event(d.strftime("%Y-%m-%d"), et)
                st.cache_data.clear(); st.success("저장됨"); st.rerun()
    with t3:
        st.info("💡 여러 개의 엑셀 파일을 한 번에 업로드하면 근무 이력을 자동 분석하여 DB에 저장합니다.")
        up_files = st.file_uploader("배차일지 엑셀 파일 (.xlsx)", type=['xlsx'], accept_multiple_files=True)
        if up_files:
            if st.button("분석 및 DB 저장 실행", type="primary"):
                with st.spinner(f"{len(up_files)}개 파일 분석 중..."):
                    try:
                        all_dfs = []
                        for up_file in up_files:
                            df_res = parse_roster_excel(up_file)
                            all_dfs.append(df_res)
                        if all_dfs:
                            final_df = pd.concat(all_dfs, ignore_index=True)
                            cnt = save_work_history(final_df)
                            st.success(f"✅ 총 {cnt}건의 신규 근무 이력이 저장/갱신되었습니다!")
                        else: st.warning("분석할 데이터가 없습니다.")
                    except Exception as e:
                        st.error(f"실패: {e}")
                        st.code(traceback.format_exc())
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
                add_reduction_rule(g_start, g_end, g_route, g_seq, g_cond)
                st.success("규칙 추가됨"); st.rerun()
        st.divider()
        try:
            rules_df = utils.load_data("reduction_rules")
            if not rules_df.empty: st.dataframe(rules_df)
        except: st.caption("등록된 규칙 없음")
