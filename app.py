      1 import streamlit as st
      2 import pandas as pd
      3 from datetime import datetime, timedelta
      4 import calendar
      5 import hashlib
      6 import gspread
      7 from oauth2client.service_account import ServiceAccountCredentials
      8 import json
      9 import time
     10 import traceback
     11 import holidays
     12 import re
     13 import io
     14
     15 # ==========================================
     16 # 0. 전역 상수 및 콜백 함수 (최상단 배치)
     17 # ==========================================
     18 WEEKDAY_KOREAN = ["월", "화", "수", "목", "금", "토", "일"]
     19 SORT_ORDER = {"휴무": 1, "교육": 2, "경조사": 3, "징계": 4, "당일 해지": 5, "기타": 6, "휴직": 7, "병가": 8}
     20
     21 def get_kst_now():
     22     return datetime.utcnow() + timedelta(hours=9)
     23
     24 # [핵심] 버튼 클릭 시 Session State와 Selectbox Key를 동시에 동기화
     25 def prev_cal_callback():
     26     if st.session_state.view_month == 1:
     27         st.session_state.view_year -= 1
     28         st.session_state.view_month = 12
     29     else:
     30         st.session_state.view_month -= 1
     31     # Selectbox 동기화
     32     st.session_state.sb_view_year = st.session_state.view_year
     33     st.session_state.sb_view_month = st.session_state.view_month
     34
     35 def next_cal_callback():
     36     if st.session_state.view_month == 12:
     37         st.session_state.view_year += 1
     38         st.session_state.view_month = 1
     39     else:
     40         st.session_state.view_month += 1
     41     # Selectbox 동기화
     42     st.session_state.sb_view_year = st.session_state.view_year
     43     st.session_state.sb_view_month = st.session_state.view_month
     44
     45 def prev_month_indiv():
     46     if st.session_state.indiv_view_month == 1:
     47         st.session_state.indiv_view_year -= 1
     48         st.session_state.indiv_view_month = 12
     49     else:
     50         st.session_state.indiv_view_month -= 1
     51     # Selectbox 동기화
     52     st.session_state.sb_ind_year = st.session_state.indiv_view_year
     53     st.session_state.sb_ind_month = st.session_state.indiv_view_month
     54
     55 def next_month_indiv():
     56     if st.session_state.indiv_view_month == 12:
     57         st.session_state.indiv_view_year += 1
     58         st.session_state.indiv_view_month = 1
     59     else:
     60         st.session_state.indiv_view_month += 1
     61     # Selectbox 동기화
     62     st.session_state.sb_ind_year = st.session_state.indiv_view_year
     63     st.session_state.sb_ind_month = st.session_state.indiv_view_month
     64
     65 if 'system_logs' not in st.session_state:
     66     st.session_state['system_logs'] = []
     67
     68 if 'last_error_msg' not in st.session_state:
     69     st.session_state['last_error_msg'] = None
     70
     71 if 'action_logs' not in st.session_state:
     72     st.session_state['action_logs'] = []
     73
     74 def add_log(msg, ids=None, sheet_name=None, level="INFO"):
     75     timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
     76     log_entry = {
     77         "time": timestamp,
     78         "msg": msg,
     79         "level": level,
     80         "ids": ids if ids else [],
     81         "sheet": sheet_name,
     82         "status": "active"
     83     }
     84     st.session_state['action_logs'].insert(0, log_entry)
     85
     86 def log_login_access(username, name):
     87     try:
     88         sh = get_db_connection()
     89         try:
     90             ws = sh.worksheet("access_logs")
     91         except gspread.exceptions.WorksheetNotFound:
     92             ws = sh.add_worksheet(title="access_logs", rows=1000, cols=4)
     93             ws.append_row(["timestamp", "username", "name", "status"])
     94         timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
     95         ws.append_row([timestamp, username, name, "Login Success"])
     96         st.cache_data.clear()
     97     except: pass
     98
     99 # ==========================================
    100 # 1. DB 연결 (영구 캐싱)
    101 # ==========================================
    102 @st.cache_resource
    103 def get_cached_sheet_object():
    104     scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    105     try:
    106         if "gcp_json" in st.secrets:
    107             creds_dict = json.loads(st.secrets["gcp_json"])
    108         else:
    109             creds_dict = dict(st.secrets["gcp_service_account"])
    110             if "private_key" in creds_dict:
    111                 creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    112
    113         creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    114         client = gspread.authorize(creds)
    115         sh = client.open("bus_schedule_db")
    116         return sh
    117     except Exception as e:
    118         st.error(f"❌ 구글 연결 실패: {e}")
    119         return None
    120
    121 def get_db_connection():
    122     sh = get_cached_sheet_object()
    123     if sh: return sh
    124     st.stop()
    125
    126 @st.cache_data(ttl=600)
    127 def load_data(sheet_name):
    128     sh = get_db_connection()
    129     try:
    130         worksheet = sh.worksheet(sheet_name)
    131         data = worksheet.get_all_values()
    132         if not data: return pd.DataFrame()
    133         headers = data.pop(0)
    134         return pd.DataFrame(data, columns=headers)
    135     except gspread.exceptions.WorksheetNotFound:
    136         return pd.DataFrame()
    137
    138 def clear_cache_after_save():
    139     st.cache_data.clear()
    140
    141 # ==========================================
    142 # 2. 실행 취소 및 계정 관리
    143 # ==========================================
    144 def delete_rows_by_ids(sheet_name, id_list):
    145     if not id_list: return False
    146     sh = get_db_connection()
    147     ws = sh.worksheet(sheet_name)
    148     col_values = ws.col_values(1)
    149     rows_to_delete = []
    150     for target_id in id_list:
    151         try:
    152             row_idx = col_values.index(target_id) + 1
    153             rows_to_delete.append(row_idx)
    154         except ValueError: continue
    155     rows_to_delete.sort(reverse=True)
    156     for r_idx in rows_to_delete:
    157         ws.delete_rows(r_idx)
    158     clear_cache_after_save()
    159     return True
    160
    161 def make_hash(password):
    162     return hashlib.sha256(str(password).encode()).hexdigest()
    163
    164 def login_user(username, password):
    165     df = load_data("users")
    166     if df.empty: return None
    167     pw_hash = make_hash(password)
    168     if 'username' not in df.columns: return None
    169     df['username'] = df['username'].astype(str)
    170     user = df[(df['username'] == username) & (df['password'] == pw_hash)]
    171     if not user.empty:
    172         return user.iloc[0]['role'], user.iloc[0]['name']
    173     return None
    174
    175 def add_user_account(username, password, role, name):
    176     sh = get_db_connection()
    177     ws = sh.worksheet("users")
    178     k_date = get_kst_now().strftime("%Y-%m-%d")
    179     new_row = [username, make_hash(password), role, name, k_date]
    180     ws.append_row(new_row)
    181     clear_cache_after_save()
    182     return True
    183
    184 def delete_user_account(username):
    185     sh = get_db_connection()
    186     ws = sh.worksheet("users")
    187     try:
    188         cell = ws.find(username)
    189         if cell:
    190             ws.delete_rows(cell.row)
    191             clear_cache_after_save()
    192     except: pass
    193
    194 def update_user_password(username, new_password):
    195     sh = get_db_connection()
    196     ws = sh.worksheet("users")
    197     try:
    198         cell = ws.find(username)
    199         if cell:
    200             ws.update_cell(cell.row, 2, make_hash(new_password))
    201             clear_cache_after_save()
    202             return True
    203     except: pass
    204     return False
    205
    206 # ==========================================
    207 # 3. 데이터 저장 로직
    208 # ==========================================
    209 def add_driver_with_group(name, group_name, start_date="2020-01-01"):
    210     sh = get_db_connection()
    211     ws_drivers = sh.worksheet("drivers")
    212     created_at = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    213     try:
    214         existing = ws_drivers.find(name)
    215         if not existing:
    216             ws_drivers.append_row(["", name, group_name, created_at, ""])
    217     except: pass
    218     ws_history = sh.worksheet("group_history")
    219     ws_history.append_row(["", name, group_name, start_date, created_at])
    220     clear_cache_after_save()
    221     return True
    222
    223 def set_driver_resignation(name, r_date):
    224     sh = get_db_connection()
    225     ws = sh.worksheet("drivers")
    226     try:
    227         cell = ws.find(name)
    228         if cell:
    229             ws.update_cell(cell.row, 5, r_date)
    230             clear_cache_after_save()
    231     except: pass
    232
    233 def delete_driver(driver_name):
    234     sh = get_db_connection()
    235     ws_d = sh.worksheet("drivers")
    236     try:
    237         cell = ws_d.find(driver_name)
    238         if cell: ws_d.delete_rows(cell.row)
    239     except: pass
    240     ws_h = sh.worksheet("group_history")
    241     try:
    242         cells = ws_h.findall(driver_name)
    243         for cell in reversed(cells): ws_h.delete_rows(cell.row)
    244     except: pass
    245     ws_s = sh.worksheet("schedules")
    246     try:
    247         cells = ws_s.findall(driver_name)
    248         for cell in reversed(cells): ws_s.delete_rows(cell.row)
    249     except: pass
    250     clear_cache_after_save()
    251
    252 def save_range_batch(name_list, start, end, type, shift, note):
    253     dates = pd.date_range(start, end)
    254     now_kst = get_kst_now()
    255     created_at = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    256     base_id = now_kst.strftime("%y%m%d%H%M")
    257
    258     rows_to_add = []
    259     generated_ids = []
    260     count = 0
    261     for name in name_list:
    262         for d in dates:
    263             d_str = d.strftime("%Y-%m-%d")
    264             row_id = f"{base_id}{count:02d}"
    265             generated_ids.append(row_id)
    266             rows_to_add.append([row_id, name, d_str, type, note, created_at, shift])
    267             count += 1
    268
    269     if rows_to_add:
    270         sh = get_db_connection()
    271         ws = sh.worksheet("schedules")
    272         ws.append_rows(rows_to_add)
    273         clear_cache_after_save()
    274
    275     return len(rows_to_add), generated_ids
    276
    277 def add_company_event(date, title):
    278     sh = get_db_connection()
    279     ws = sh.worksheet("company_events")
    280     now_kst = get_kst_now()
    281     created_at = now_kst.strftime("%Y-%m-%d")
    282     row_id = now_kst.strftime("%y%m%d%H%M%S")
    283     ws.append_row([row_id, date, title, created_at])
    284     clear_cache_after_save()
    285     return row_id
    286
    287 # ==========================================
    288 # 4. [모듈] 배차일지 분석 및 감차(Reduction) 엔진
    289 # ==========================================
    290 kr_holidays = holidays.KR()
    291
    292 def is_holiday_or_weekend(date_obj):
    293     return date_obj.weekday() >= 5 or date_obj in kr_holidays
    294
    295 def clean_driver_name(name):
    296     if pd.isna(name): return ""
    297     s = str(name).strip()
    298     if s.lower() == "nan" or s == "": return ""
    299     s = re.sub(r'\(.*?\)', '', s)
    300     s = s.replace(" ", "").strip()
    301     return s
    302
    303 def get_reduction_rules():
    304     df = load_data("reduction_rules")
    305     rules = []
    306     if not df.empty and 'start_date' in df.columns:
    307         for _, row in df.iterrows():
    308             rules.append({
    309                 'start': row['start_date'],
    310                 'end': row['end_date'],
    311                 'route': str(row['route']).strip(),
    312                 'seq': str(row['sequence']).strip(),
    313                 'condition': row['condition']
    314             })
    315     return rules
    316
    317 def is_reduction_target(date_str, route, seq, rules):
    318     try:
    319         d = datetime.strptime(date_str, "%Y-%m-%d").date()
    320     except: return False
    321     is_holi = is_holiday_or_weekend(d)
    322     for r in rules:
    323         if r['start'] <= date_str <= r['end']:
    324             if r['route'] == route and r['seq'] == seq:
    325                 if r['condition'] == 'Always': return True
    326                 if r['condition'] == 'Weekend/Holiday' and is_holi: return True
    327     return False
    328
    329 def parse_roster_excel(file):
    330     df_raw = pd.read_excel(file, header=None)
    331     date_rows = []
    332     for idx, row in df_raw.iterrows():
    333         val = str(row[0])
    334         if "202" in val or "년" in val:
    335             try:
    336                 if pd.notnull(df_raw.iloc[idx, 3]) and pd.notnull(df_raw.iloc[idx, 5]):
    337                     date_rows.append(idx)
    338             except: pass
    339
    340     extracted_data = []
    341
    342     for start_row in date_rows:
    343         try:
    344             year = int(str(df_raw.iloc[start_row, 0]).replace("년","").strip())
    345             month = int(str(df_raw.iloc[start_row, 3]).replace("월","").strip())
    346             day = int(str(df_raw.iloc[start_row, 5]).replace("일","").strip())
    347             current_date = datetime(year, month, day).strftime("%Y-%m-%d")
    348         except: continue
    349
    350         cols_map = [
    351             {'route':1, 'seq':2, 'car':3, 'am_fix':4, 'am_sub':5, 'pm_fix':6, 'pm_sub':7}, # Left
    352             {'route':9, 'seq':10, 'car':11, 'am_fix':12, 'am_sub':13, 'pm_fix':14, 'pm_sub':15} # Right
    353         ]
    354
    355         for side in cols_map:
    356             last_route = None
    357             for r_offset in range(3, 75):
    358                 curr_idx = start_row + r_offset
    359                 if curr_idx >= len(df_raw): break
    360
    361                 raw_route = df_raw.iloc[curr_idx, side['route']]
    362                 if pd.notnull(raw_route) and str(raw_route).strip() != "":
    363                     last_route = str(raw_route).strip()
    364                 current_route = last_route if last_route else ""
    365
    366                 raw_seq = df_raw.iloc[curr_idx, side['seq']]
    367                 raw_car = df_raw.iloc[curr_idx, side['car']]
    368
    369                 current_seq = str(raw_seq).strip() if pd.notnull(raw_seq) else ""
    370
    371                 # 감차 로직 추가
    372                 is_reduction = False
    373                 is_valid_car = False
    374                 current_car = ""
    375                 raw_car_str = str(raw_car).strip()
    376
    377                 if "감차" in raw_car_str:
    378                     is_reduction = True
    379                     current_car = "감차"
    380                 else:
    381                     try:
    382                         digits_only = re.sub(r'[^0-9]', '', raw_car_str)
    383                         if digits_only:
    384                             car_num = int(digits_only)
    385                             if 5001 <= car_num <= 5300:
    386                                 is_valid_car = True
    387                                 current_car = str(car_num)
    388                     except:
    389                         is_valid_car = False
    390                         current_car = ""
    391
    392                 if not (current_route and current_seq):
    393                     continue
    394
    395                 am_fix = clean_driver_name(df_raw.iloc[curr_idx, side['am_fix']])
    396                 pm_fix = clean_driver_name(df_raw.iloc[curr_idx, side['pm_fix']])
    397
    398                 if is_reduction:
    399                     if am_fix:
    400                         extracted_data.append({
    401                             'date': current_date, 'name': am_fix, 'shift': '감차휴무',
    402                             'route': current_route, 'seq': current_seq, 'car': '감차',
    403                             'is_sub': 'FALSE', 'orig_fix': am_fix, 'updated_at': get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    404                         })
    405                     if pm_fix:
    406                         extracted_data.append({
    407                             'date': current_date, 'name': pm_fix, 'shift': '감차휴무',
    408                             'route': current_route, 'seq': current_seq, 'car': '감차',
    409                             'is_sub': 'FALSE', 'orig_fix': pm_fix, 'updated_at': get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    410                         })
    411                     continue
    412
    413                 if not is_valid_car:
    414                     continue
    415
    416                 am_sub = clean_driver_name(df_raw.iloc[curr_idx, side['am_sub']])
    417                 am_final = am_sub if am_sub else am_fix
    418
    419                 pm_sub = clean_driver_name(df_raw.iloc[curr_idx, side['pm_sub']])
    420                 pm_final = pm_sub if pm_sub else pm_fix
    421
    422                 if am_final:
    423                     extracted_data.append({
    424                         'date': current_date, 'name': am_final, 'shift': '오전',
    425                         'route': current_route, 'seq': current_seq, 'car': current_car,
    426                         'is_sub': str(bool(am_sub)).upper(), 'orig_fix': am_fix, 'updated_at': get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    427                     })
    428
    429                 if pm_final:
    430                     extracted_data.append({
    431                         'date': current_date, 'name': pm_final, 'shift': '오후',
    432                         'route': current_route, 'seq': current_seq, 'car': current_car,
    433                         'is_sub': str(bool(pm_sub)).upper(), 'orig_fix': pm_fix, 'updated_at': get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    434                     })
    435     return pd.DataFrame(extracted_data)
    436
    437 def save_work_history(df_new):
    438     sh = get_db_connection()
    439     try:
    440         ws = sh.worksheet("work_history")
    441     except gspread.exceptions.WorksheetNotFound:
    442         ws = sh.add_worksheet(title="work_history", rows=1000, cols=10)
    443         ws.append_row(['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at'])
    444
    445     existing_data = ws.get_all_values()
    446     df_old = pd.DataFrame()
    447     if len(existing_data) > 1:
    448         headers = existing_data.pop(0)
    449         df_old = pd.DataFrame(existing_data, columns=headers)
    450
    451     if df_old.empty:
    452         df_final = df_new
    453     else:
    454         required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at']
    455         for c in required_cols:
    456             if c not in df_new.columns: df_new[c] = ""
    457             if c not in df_old.columns: df_old[c] = ""
    458
    459         df_new = df_new[required_cols]
    460         df_old = df_old[required_cols]
    461
    462         df_combined = pd.concat([df_old, df_new])
    463
    464         # 감차휴무 처리 로직
    465         # 1. 실제 근무 기록이 있는 (날짜, 이름) 조합을 찾음
    466         actually_worked = df_combined[df_combined['shift'] != '감차휴무'][['date', 'name']].drop_duplicates()
    467         actually_worked['worked_flag'] = True
    468
    469         # 2. 원본 데이터와 합쳐서 근무 여부 플래그를 달아줌
    470         df_merged = pd.merge(df_combined, actually_worked, on=['date', 'name'], how='left')
    471
    472         # 3. 근무 플래그가 True인데 shift가 '감차휴무'인 행을 필터링하여 제거
    473         df_final = df_merged[~((df_merged['worked_flag'] == True) & (df_merged['shift'] == '감차휴무'))]
    474
    475         # 4. 최종적으로 중복 제거 및 정렬
    476         df_final = df_final.drop(columns=['worked_flag'])
    477         df_final = df_final.drop_duplicates(subset=['date', 'name', 'shift'], keep='last')
    478
    479     df_final = df_final.sort_values(by=['date', 'name'])
    480
    481     ws.clear()
    482     ws.append_row(['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub', 'orig_fix', 'updated_at'])
    483
    484     data_to_write = df_final.fillna("").astype(str).values.tolist()
    485     if data_to_write:
    486         ws.append_rows(data_to_write)
    487
    488     clear_cache_after_save()
    489     return len(df_new)
    490
    491 def add_reduction_rule(start, end, route, seq, cond):
    492     sh = get_db_connection()
    493     try:
    494         ws = sh.worksheet("reduction_rules")
    495     except:
    496         ws = sh.add_worksheet(title="reduction_rules", rows=100, cols=5)
    497         ws.append_row(['start_date', 'end_date', 'route', 'sequence', 'condition'])
    498
    499     ws.append_row([str(start), str(end), str(route), str(seq), cond])
    500     clear_cache_after_save()
    501
    502 # ==========================================
    503 # 5. 로직 및 계산
    504 # ==========================================
    505 def calculate_auto_shift(group_name, target_date_str):
    506     if not group_name or "조" not in group_name: return None
    507     try:
    508         ref = datetime(2025, 12, 1)
    509         tgt = datetime.strptime(target_date_str, "%Y-%m-%d")
    510         pat = ["오전", "오전", "오전", "오전", "휴무", "오후", "오후", "오후", "오후", "휴무"]
    511         offs = {"10조":0, "9조":1, "8조":2, "7조":3, "6조":4, "5조":5, "4조":6, "3조":7, "2조":8, "1조":9}
    512         off = offs.get(group_name)
    513         if off is None: return None
    514         return pat[((tgt - ref).days + off) % 10]
    515     except: return None
    516
    517 def get_group_from_dict(history_dict, name, target_date_str):
    518     if name not in history_dict: return None
    519     records = history_dict[name]
    520     for start_date, group in records:
    521         if start_date <= target_date_str:
    522             return group
    523     return None
    524
    525 def get_type_color(type_name):
    526     colors = {
    527         "휴무": "#00592D", "교육": "#8c6b4a", "경조사": "#1F3994",
    528         "징계": "#000000", "당일 해지": "#8B0000", "병가": "#A52A2A",
    529         "휴직": "#D2691E", "육아휴직": "#D2691E", "기타": "#363636",
    530         "실제근무_본인": "#1e88e5", # 파랑
    531         "실제근무_대운": "#8e24aa",  # 보라
    532         "감차휴무": "#6c757d" # 회색
    533     }
    534     return colors.get(type_name, "#546E7A")
    535
    536 def get_off_groups(date_str):
    537     ref = datetime(2025, 12, 1)
    538     target = datetime.strptime(date_str, "%Y-%m-%d")
    539     cycle = (target - ref).days % 5
    540     return [("1,6조", ["1조", "6조"]), ("2,7조", ["2조", "7조"]), ("3,8조", ["3조", "8조"]), ("4,9조", ["4조", "9조"]), ("5,10조", ["5조", "10조"])][cycle]
    541
    542 def is_holiday(date_obj):
    543     return date_obj in kr_holidays
    544
    545 def get_daily_shift_summary(date_str):
    546     am, pm = [], []
    547     off_from_am, off_from_pm = [], []
    548     prev_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    549     for i in range(1, 11):
    550         grp_name = f"{i}조"
    551         s = calculate_auto_shift(grp_name, date_str)
    552         if s == "오전": am.append(str(i))
    553         elif s == "오후": pm.append(str(i))
    554         else:
    555             prev_s = calculate_auto_shift(grp_name, prev_date)
    556             if prev_s == "오전": off_from_am.append(str(i))
    557             else: off_from_pm.append(str(i))
    558     line1 = f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:1px;'><span style='color:#1c7ed6; font-weight:bold;'>오전: {','.join(am)}</span><span
        style='color:#868e96; font-size:0.85em; font-weight:bold;'>휴무: {','.join(off_from_am)}</span></div>"
    559     line2 = f"<div style='display:flex; justify-content:space-between; align-items:center;'><span style='color:#d9480f; font-weight:bold;'>오후: {','.join(pm)}</span><span style='color:#868e96;
        font-size:0.85em; font-weight:bold;'>휴무: {','.join(off_from_pm)}</span></div>"
    560     return line1 + line2
    561
    562 @st.cache_data(ttl=600)
    563 def calculate_layout_rows(df_month):
    564     if df_month.empty: return {}, 0
    565     df_sorted = df_month.sort_values(by=['name', 'date'])
    566     segments = []
    567     if not df_sorted.empty:
    568         curr = df_sorted.iloc[0]
    569         c_name, c_type, c_start, c_end = curr['name'], curr['type'], curr['date'], curr['date']
    570         c_recs = [curr]
    571         for i in range(1, len(df_sorted)):
    572             row = df_sorted.iloc[i]
    573             pd_date = datetime.strptime(c_end, "%Y-%m-%d")
    574             cd = datetime.strptime(row['date'], "%Y-%m-%d")
    575             if row['name'] == c_name and row['type'] == c_type and (cd - pd_date).days == 1:
    576                 c_end = row['date']
    577                 c_recs.append(row)
    578             else:
    579                 segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
    580                 c_name, c_type, c_start, c_end = row['name'], row['type'], row['date'], row['date']
    581                 c_recs = [row]
    582         segments.append({'name': c_name, 'type': c_type, 'start': c_start, 'end': c_end, 'records': c_recs})
    583
    584     segments.sort(key=lambda x: (SORT_ORDER.get(x['type'], 99), x['start'], (datetime.strptime(x['end'], "%Y-%m-%d") - datetime.strptime(x['start'], "%Y-%m-%d")).days * -1))
    585     lanes = {}
    586     layout_map = {}
    587     for seg in segments:
    588         seg_dates = [rec['date'] for rec in seg['records']]
    589         assigned_row = 0
    590         while True:
    591             is_occupied = False
    592             if assigned_row in lanes:
    593                 for d in seg_dates:
    594                     if d in lanes[assigned_row]:
    595                         is_occupied = True
    596                         break
    597             if not is_occupied: break
    598             assigned_row += 1
    599         if assigned_row not in lanes: lanes[assigned_row] = set()
    600         lanes[assigned_row].update(seg_dates)
    601         recs = seg['records']
    602         total_len = len(recs)
    603         for idx, rec in enumerate(recs):
    604             is_start = (idx == 0)
    605             is_end = (idx == total_len - 1)
    606             layout_map[(rec['date'], assigned_row)] = { 'rec': rec, 'is_start': is_start, 'is_end': is_end, 'duration': total_len }
    607     max_row = max(lanes.keys()) + 1 if lanes else 0
    608     return layout_map, max_row
    609
    610 def get_stats_optimized(date_str, all_drivers_df, today_schedules_df, history_dict):
    611     active_drivers_list = []
    612     if not all_drivers_df.empty:
    613         has_resign_col = 'resigned_date' in all_drivers_df.columns
    614         for _, dr in all_drivers_df.iterrows():
    615             is_active = True
    616             if has_resign_col:
    617                 r_date = str(dr['resigned_date']).strip()
    618                 if r_date and date_str > r_date: is_active = False
    619             if is_active: active_drivers_list.append(dr['name'])
    620
    621     total = len(active_drivers_list)
    622     am_cnt, pm_cnt, off_cnt = 0, 0, 0
    623     manual_map = {}
    624     if not today_schedules_df.empty:
    625         for _, row in today_schedules_df.iterrows():
    626             manual_map[row['name']] = (row['type'], row.get('shift', '자동'))
    627
    628     for name in active_drivers_list:
    629         final_shift = None
    630         if name in manual_map:
    631             typ, sft = manual_map[name]
    632             if typ == '휴무': final_shift = '휴무'
    633             elif sft and sft != '자동': final_shift = sft
    634         if not final_shift:
    635             grp = get_group_from_dict(history_dict, name, date_str)
    636             if grp: final_shift = calculate_auto_shift(grp, date_str)
    637         if final_shift == '오전': am_cnt += 1
    638         elif final_shift == '오후': pm_cnt += 1
    639         elif final_shift == '휴무': off_cnt += 1
    640
    641     full_text = f"총 {total}명 (오전:{am_cnt}, 오후:{pm_cnt}, 휴무:{off_cnt})"
    642     short_text = f"총 {total} / 전 {am_cnt} / 후 {pm_cnt}"
    643     return full_text, short_text
    644
    645 def get_streak_info(full_schedule_map, p_name, p_date_str, p_type):
    646     if (p_name, p_date_str) not in full_schedule_map: return "", "", ""
    647     curr = datetime.strptime(p_date_str, "%Y-%m-%d")
    648     start_date, end_date = curr, curr
    649     while True:
    650         prev_d = (start_date - timedelta(days=1)).strftime("%Y-%m-%d")
    651         if (p_name, prev_d) in full_schedule_map and full_schedule_map[(p_name, prev_d)] == p_type: start_date -= timedelta(days=1)
    652         else: break
    653     while True:
    654         next_d = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
    655         if (p_name, next_d) in full_schedule_map and full_schedule_map[(p_name, next_d)] == p_type: end_date += timedelta(days=1)
    656         else: break
    657     duration = (end_date - start_date).days + 1
    658     prefix, suffix = "", ""
    659     period_text = f"(~{end_date.month}/{end_date.day})"
    660     if duration >= 2:
    661         is_start = (p_date_str == start_date.strftime("%Y-%m-%d"))
    662         is_end = (p_date_str == end_date.strftime("%Y-%m-%d"))
    663         if is_start: prefix = "➡️";
    664         if is_end: suffix = "🛑"
    665     return prefix, suffix, period_text
    666
    667 # ==========================================
    668 # 6. 화면 렌더링
    669 # ==========================================
    670 def inject_custom_css():
    671     st.markdown("""
    672     <style>
    673         .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
    674         div[data-testid="column"] { padding: 0px !important; gap: 0px !important; }
    675         .horizontal-scroll-container { display: flex; overflow-x: auto; gap: 0px; padding-bottom: 15px; width: 100%; }
    676
    677         /* [수정] 박스 그림자 적용 (테두리 두께로 인한 밀림 방지) */
    678         .calendar-day-box {
    679             border: 1px solid #e9ecef;
    680             min-height: 200px;
    681             padding: 0;
    682             background-color: white;
    683             display: flex;
    684             flex-direction: column;
    685             height: auto !important;
    686         }
    687
    688         .calendar-day-box-horiz { flex: 0 0 90px; }
    689         .calendar-day-box-grid { width: 100%; margin: 2px; }
    690
    691         .horizontal-scroll-container::-webkit-scrollbar { height: 8px; }
    692         .horizontal-scroll-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
    693         .horizontal-scroll-container::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
    694         .horizontal-scroll-container::-webkit-scrollbar-thumb:hover { background: #aaa; }
    695         .daily-stats-box { background-color: #f1f3f5; border-bottom: 1px solid #e9ecef; font-size: 11px; text-align: center; padding: 3px 0; color: #495057; font-weight: bold; white-space: nowrap; }
    696         .group-info-box { font-size: 10px; padding: 2px 4px; background-color: #fff; border-bottom: 1px solid #f1f3f5; line-height: 1.2; font-weight: bold; }
    697         .event-container { height: 46px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; border-bottom: 1px solid #f1f3f5; padding: 2px 1px; background-color: #fff; }
    698         .event-container::-webkit-scrollbar { display: none; }
    699         .day-header { display: flex; flex-direction: column; padding-top: 4px; padding-bottom: 4px; gap: 1px; justify-content: center; background-color: transparent; border-bottom: 1px solid #eee; }
    700
    701         .schedule-bar { color: white; padding: 0 2px; margin-bottom: 1px; line-height: 1.1; text-align: center; cursor: help; font-size: 11px; height: 34px; display: flex; flex-direction: column;
        justify-content: center; overflow: hidden; border-top: none; border-bottom: none; }
    702         .bar-start { border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0; border-bottom-right-radius: 0; margin-right: -10px !important; margin-left: 2px; position:
        relative; z-index: 2; }
    703         .bar-mid { border-radius: 0; border-left: none; border-right: none; margin-left: -10px !important; margin-right: -10px !important; position: relative; z-index: 1; }
    704         .bar-end { border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-top-left-radius: 0; border-bottom-left-radius: 0; margin-left: -10px !important; margin-right: 2px; position:
        relative; z-index: 2; }
    705         .bar-single { border-radius: 4px; margin: 0 2px 1px 2px; z-index: 3; }
    706         .schedule-spacer { height: 34px; margin-bottom: 1px; background-color: transparent; }
    707
    708         /* [수정] 로그인 버튼 - 초강력 CSS 우선순위 적용 */
    709         button[kind="primary"], div[data-testid="stButton"] button {
    710             background-color: #00592D !important;
    711             border-color: #00592D !important;
    712             color: white !important;
    713         }
    714         button[kind="primary"]:hover, div[data-testid="stButton"] button:hover {
    715             background-color: #004d26 !important;
    716             border-color: #004d26 !important;
    717             color: white !important;
    718         }
    719
    720         @media (max-width: 640px) { h1 { font-size: 1.6rem !important; } .mobile-font { font-size: 10px !important; } .mobile-header { font-size: 11px !important; } }
    721     </style>
    722     """, unsafe_allow_html=True)
    723
    724 @st.dialog("➕ 빠른 등록")
    725 def show_input_dialog():
    726     tab1, tab2 = st.tabs(["👤 승무원 일정", "🏢 회사 행사"])
    727     with tab1:
    728         st.write("달력을 보면서 바로 입력하세요.")
    729         names_str = st.text_area("이름 (엔터 구분)", height=100, key="quick_names")
    730         rng = st.date_input("기간", [], help="시작/종료일 선택", key="quick_range")
    731         c1, c2 = st.columns(2)
    732         with c1: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="quick_type")
    733         with c2: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="quick_shift")
    734         nte = st.text_input("비고", key="quick_note")
    735
    736         if st.button("승무원 일정 저장", type="primary", use_container_width=True):
    737             if names_str and len(rng) > 0:
    738                 lst = [n.strip() for n in names_str.replace(',', '\n').split('\n') if n.strip()]
    739                 try:
    740                     with st.spinner('저장 중입니다...'):
    741                         count, ids = save_range_batch(lst, rng[0], rng[-1], typ, sft, nte)
    742                     st.toast("✅ 저장 완료!", icon="🔄")
    743                     add_log(f"입력 성공: {len(lst)}명", ids=ids, sheet_name="schedules")
    744                     time.sleep(0.7); st.rerun()
    745                 except Exception as e: st.error("🚨 저장 중 오류 발생!")
    746             else: st.warning("이름과 기간을 입력해주세요.")
    747     with tab2:
    748         st.write("회사 주요 행사를 달력 상단에 표시합니다.")
    749         ed_list = st.date_input("행사 기간", [], help="시작/종료일", key="quick_event_range")
    750         et = st.text_input("행사 내용", key="quick_event_title")
    751         if st.button("회사 행사 저장", type="primary", use_container_width=True, key="quick_event_save"):
    752             if et and len(ed_list) > 0:
    753                 try:
    754                     with st.spinner('저장 중입니다...'):
    755                         for d in pd.date_range(ed_list[0], ed_list[-1]): add_company_event(d.strftime("%Y-%m-%d"), et)
    756                         st.cache_data.clear()
    757                     st.toast("✅ 행사 저장 완료!", icon="🔄")
    758                     add_log(f"행사 등록: {et}", sheet_name="company_events")
    759                     time.sleep(0.7); st.rerun()
    760                 except Exception: st.error("오류 발생")
    761             else: st.warning("기간과 내용을 입력해주세요.")
    762
    763 def render_log_tab():
    764     st.subheader("🔧 시스템 로그 및 실행 취소")
    765     t_act, t_acc = st.tabs(["📋 작업 로그", "👥 접속 이력"])
    766     with t_act:
    767         if st.button("🗑️ 로그 비우기"): st.session_state['action_logs'] = []; st.rerun()
    768         st.divider()
    769         for i, log in enumerate(st.session_state['action_logs']):
    770             c1, c2, c3 = st.columns([1, 4, 1])
    771             with c1: st.write(log['time'])
    772             with c2: st.write(f"{log['msg']}")
    773             with c3:
    774                 if log['status'] == 'active' and log.get('ids'):
    775                     if st.button("↩️ 실행 취소", key=f"undo_{i}"):
    776                         delete_rows_by_ids(log['sheet'], log['ids'])
    777                         log['status'] = 'canceled'; st.rerun()
    778     with t_acc:
    779         try:
    780             df_acc = load_data("access_logs")
    781             if not df_acc.empty: st.dataframe(df_acc.sort_values(by='timestamp', ascending=False), use_container_width=True)
    782             else: st.info("접속 기록이 없습니다.")
    783         except: st.warning("로그 없음")
    784
    785 def render_calendar_tab():
    786     if st.session_state.get('last_error_msg'): st.error("오류 발생"); st.code(st.session_state['last_error_msg'])
    787     try: _render_calendar_tab_unsafe()
    788     except Exception: st.error("캘린더 렌더링 오류"); st.code(traceback.format_exc())
    789
    790 def _render_calendar_tab_unsafe():
    791     # [수정] 한 줄 UI (제목, 범례, 보기방식)
    792     c_title, c_legend, c_view = st.columns([1, 1.5, 0.8])
    793     with c_title:
    794         st.markdown("### 📅 월간 휴무 신청 현황")
    795     with c_legend:
    796         types = ["휴무", "교육", "경조사", "징계", "당일 해지", "병가", "휴직", "기타"]
    797         legend_html = "<div style='display:flex; flex-wrap:wrap; gap:5px; align-items:center; height:100%; margin-top:10px;'>"
    798         for t in types:
    799             c = get_type_color(t)
    800             legend_html += f"<span style='background:{c}; color:white; border:1px solid #333; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:bold;'>{t}</span>"
    801         legend_html += "</div>"
    802         st.markdown(legend_html, unsafe_allow_html=True)
    803     with c_view:
    804         view_mode = st.radio("보기", ["가로 스크롤", "달력"], horizontal=True, label_visibility="collapsed")
    805
    806     inject_custom_css()
    807
    808     now = get_kst_now()
    809     if 'view_year' not in st.session_state:
    810         st.session_state.view_year = now.year
    811         st.session_state.sb_view_year = now.year
    812     if 'view_month' not in st.session_state:
    813         st.session_state.view_month = now.month
    814         st.session_state.sb_view_month = now.month
    815
    816     # [수정] 달력 이동 (한 줄로 배치) - UI 비율 조정
    817     c1, c2, c3, c4, c5, c6, c7 = st.columns([0.3, 0.7, 0.3, 0.7, 0.4, 0.4, 1.2])
    818     with c1: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
    819     with c2:
    820         year_range = range(2023, now.year + 3)
    821         st.selectbox("년도", year_range, index=year_range.index(st.session_state.view_year), key='sb_view_year', label_visibility="collapsed")
    822     # 동기화 로직
    823     if st.session_state.sb_view_year != st.session_state.view_year:
    824         st.session_state.view_year = st.session_state.sb_view_year
    825         st.rerun()
    826
    827     with c3: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
    828     with c4:
    829         month_range = range(1, 13)
    830         st.selectbox("월", month_range, index=month_range.index(st.session_state.view_month), key='sb_view_month', label_visibility="collapsed")
    831     # 동기화 로직
    832     if st.session_state.sb_view_month != st.session_state.view_month:
    833         st.session_state.view_month = st.session_state.sb_view_month
    834         st.rerun()
    835
    836     with c5: st.button("◀", key="prev_cal_btn", on_click=prev_cal_callback)
    837     with c6: st.button("▶", key="next_cal_btn", on_click=next_cal_callback)
    838     with c7:
    839         if st.session_state.get('auth_status') == 'admin':
    840             if st.button("➕ 빠른 입력", type="primary", use_container_width=True): show_input_dialog()
    841
    842     st.divider()
    843
    844     year, month = st.session_state.view_year, st.session_state.view_month
    845
    846     # [수정] 데이터 불러오기 및 날짜 형식 정규화 (이 부분이 핵심 수정 사항)
    847     df = load_data("schedules")
    848     if not df.empty and 'date' in df.columns:
    849         # 날짜 컬럼을 강제로 YYYY-MM-DD 형식으로 통일
    850         df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime("%Y-%m-%d")
    851         # 이름 컬럼 공백 제거
    852         if 'name' in df.columns:
    853             df['name'] = df['name'].astype(str).str.strip()
    854
    855     df_month = df[df['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df.empty else pd.DataFrame()
    856
    857     full_schedule_map = {}
    858     if not df.empty:
    859         for _, row in df.iterrows(): full_schedule_map[(row['name'], str(row['date']))] = row['type']
    860
    861     df_events = load_data("company_events")
    862     df_events_month = df_events[df_events['date'].astype(str).str.startswith(f"{year}-{month:02d}")] if not df_events.empty else pd.DataFrame()
    863
    864     all_drivers = load_data("drivers")
    865     group_history_df = load_data("group_history")
    866     history_dict = {}
    867     if not group_history_df.empty:
    868         for _, row in group_history_df.iterrows():
    869             if row['driver_name'] not in history_dict: history_dict[row['driver_name']] = []
    870             history_dict[row['driver_name']].append((row['start_date'], row['group_name']))
    871         for k in history_dict: history_dict[k].sort(key=lambda x:x[0], reverse=True)
    872
    873     _, last_day = calendar.monthrange(year, month)
    874
    875     def get_day_html(day, is_horiz=True):
    876         d_str = f"{year}-{month:02d}-{day:02d}"
    877         wd_idx = datetime(year, month, day).weekday()
    878
    879         today_sch = df_month[df_month['date'] == d_str] if not df_month.empty else pd.DataFrame()
    880         today_evt = df_events_month[df_events_month['date'] == d_str] if not df_events_month.empty else pd.DataFrame()
    881
    882         full_stat, short_stat = get_stats_optimized(d_str, all_drivers, today_sch, history_dict)
    883
    884         # [수정] 하이라이트 범위 확대 (박스 전체)
    885         box_style = ""
    886
    887         if d_str == now.strftime("%Y-%m-%d"):
    888             box_style = "box-shadow: inset 0 0 0 2px #fbc02d; background-color: #fff9c4;" # 노랑 (오늘)
    889
    890         elif d_str == (now + timedelta(days=1)).strftime("%Y-%m-%d"):
    891             box_style = "box-shadow: inset 0 0 0 1px #ef5350; background-color: #ffebee;" # 연한 빨강 (내일)
    892         else:
    893             box_style = "background-color: white;"
    894
    895         day_color = "#333"
    896         if wd_idx == 6 or is_holiday(datetime(year, month, day)): day_color = "#d32f2f"
    897         elif wd_idx == 5: day_color = "#1976D2"
    898
    899         # [수정] 박스 전체에 스타일 적용
    900         html = f'<div class="calendar-day-box {"calendar-day-box-horiz" if is_horiz else "calendar-day-box-grid"}" style="{box_style}">'
    901         html += f'<div class="day-header"><div style="display:flex; justify-content:space-between; padding:0 3px;"><span style="font-weight:bold; color:{day_color};">{day}일({WEEKDAY_KOREAN[wd_idx]}
        )</span><span style="font-size:11px;">{len(today_sch)}명</span></div>'
    902         html += f'<div class="group-info-box">{get_daily_shift_summary(d_str)}</div></div>'
    903         if is_horiz: html += f'<div class="daily-stats-box" title="{full_stat}">{short_stat}</div>'
    904
    905         html += '<div class="event-container">'
    906         if not today_evt.empty:
    907             for _, e in today_evt.iterrows(): html += f"<div style='background:#E3F2FD; color:#1565C0; font-size:10px; text-align:center;'>{e['title']}</div>"
    908         html += '</div>'
    909
    910         if not is_horiz and not today_sch.empty:
    911             today_sch['rank'] = today_sch['type'].map(lambda x: SORT_ORDER.get(x, 99))
    912             today_sch = today_sch.sort_values(by=['rank', 'name'])
    913             for _, row in today_sch.iterrows():
    914                 col = get_type_color(row['type'])
    915                 pre, suf, period_text = get_streak_info(full_schedule_map, row['name'], d_str, row['type'])
    916                 grp = get_group_from_dict(history_dict, row['name'], d_str)
    917                 orig = calculate_auto_shift(grp, d_str)
    918
    919                 orig_mk = ""
    920                 if orig == '오전': orig_mk = "<span style='color:#87CEEB; font-weight:bold;'>(전)</span> "
    921                 elif orig == '오후': orig_mk = "<span style='color:#FFB6C1; font-weight:bold;'>(후)</span> "
    922
    923                 inner = f"""<div style="position:relative; width:100%; display:flex; justify-content:center; align-items:center;">
    924                         <div style="position:absolute; left:2px;">{pre}</div>
    925                         <div style="width:100%; text-align:center; overflow:hidden; text-overflow:ellipsis; padding:0 14px;">{row['name']}</div>
    926                         <div style="position:absolute; right:2px;">{suf}</div></div>"""
    927
    928                 n_txt = row['note'] if row['note'] else row['type']
    929                 if period_text: n_txt += f" {period_text}"
    930
    931                 sub_txt = f"<div style='font-size:9px; opacity:0.9;'>{orig_mk}{n_txt}</div>"
    932                 html += f"<div class='schedule-bar bar-single' style='background:{col}; border:3px solid #222; color:white;' title='원래: {orig} ({grp})'>{inner}{sub_txt}</div>"
    933         html += '</div>'
    934         return html
    935
    936     if "가로" in view_mode:
    937         l_map, m_row = calculate_layout_rows(df_month)
    938         h_html = '<div class="horizontal-scroll-container">'
    939         for d in range(1, last_day+1):
    940             d_str = f"{year}-{month:02d}-{d:02d}"
    941             h_html += get_day_html(d, True)[:-6]
    942             for r in range(m_row):
    943                 if (d_str, r) in l_map:
    944                     it = l_map[(d_str, r)]
    945                     row = it['rec']
    946                     col = get_type_color(row['type'])
    947                     pre, suf, period_text = get_streak_info(full_schedule_map, row['name'], d_str, row['type'])
    948
    949                     grp = get_group_from_dict(history_dict, row['name'], d_str)
    950                     orig = calculate_auto_shift(grp, d_str)
    951                     orig_mk = ""
    952                     if orig == '오전': orig_mk = "<span style='color:#87CEEB; font-weight:bold;'>(전)</span> "
    953                     elif orig == '오후': orig_mk = "<span style='color:#FFB6C1; font-weight:bold;'>(후)</span> "
    954
    955                     inner = f"""<div style="position:relative; width:100%; display:flex; justify-content:center; align-items:center;">
    956                             <div style="position:absolute; left:2px;">{pre}</div>
    957                             <div style="width:100%; text-align:center; overflow:hidden; text-overflow:ellipsis; padding:0 14px;">{row['name']}</div>
    958                             <div style="position:absolute; right:2px;">{suf}</div></div>"""
    959
    960                     n_txt = row['note'] if row['note'] else row['type']
    961                     if period_text: n_txt += f" {period_text}"
    962
    963                     sub = f"<div style='font-size:9px; opacity:0.9;'>{orig_mk}{n_txt}</div>"
    964
    965                     cls = "bar-single"
    966                     b_style = "border:3px solid #222;"
    967                     if it['duration'] >= 2:
    968                         if it['is_start']: cls = "bar-start"; b_style="border-top:3px solid #222; border-bottom:3px solid #222; border-left:3px solid #222;"
    969                         elif it['is_end']: cls = "bar-end"; b_style="border-top:3px solid #222; border-bottom:3px solid #222; border-right:3px solid #222;"
    970                         else: cls = "bar-mid"; b_style="border-top:3px solid #222; border-bottom:3px solid #222;"
    971
    972                     h_html += f"<div class='schedule-bar {cls}' style='background:{col}; {b_style} color:white;'>{inner}{sub}</div>"
    973                 else: h_html += "<div class='schedule-spacer'></div>"
    974             h_html += "</div>"
    975         h_html += "</div>"
    976         st.markdown(h_html, unsafe_allow_html=True)
    977     else:
    978         cols = st.columns(7)
    979         for i, w in enumerate(WEEKDAY_KOREAN): cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:{'#d32f2f' if i==6 else '#1976D2' if i==5 else 'black'};'>{w}</div>",
        unsafe_allow_html=True)
    980         for week in calendar.monthcalendar(year, month):
    981             cols = st.columns(7)
    982             for i, d in enumerate(week):
    983                 with cols[i]:
    984                     if d == 0: st.markdown("<div class='calendar-day-box' style='background:#f8f9fa;'></div>", unsafe_allow_html=True)
    985                     else: st.markdown(get_day_html(d, False), unsafe_allow_html=True)
    986
    987 def render_input_tab():
    988     st.subheader("📝 관리자 입력 & 배차 관리")
    989     t1, t2, t3, t4 = st.tabs(["휴무 등록", "행사 등록", "📂 배차일지 업로드", "⚙️ 감차 규칙"])
    990     with t1:
    991         c1, c2 = st.columns([2, 1])
    992         with c1: names_str = st.text_area("이름 (엔터 구분)", height=68, key="tab_names")
    993         with c2: rng = st.date_input("기간", [], help="시작/종료일 선택", key="tab_range")
    994         c3, c4 = st.columns(2)
    995         with c3: typ = st.selectbox("구분", ["휴무", "교육", "경조사", "병가", "휴직", "징계", "당일 해지", "기타"], key="tab_type")
    996         with c4: sft = st.selectbox("근무", ["자동", "오전", "오후", "휴무", "기타"], key="tab_shift")
    997         nte = st.text_input("비고", key="tab_note")
    998         st.markdown('<div class="red-button">', unsafe_allow_html=True)
    999         if st.button("일괄 저장", type="primary", use_container_width=True):
   1000             if names_str and len(rng) > 0:
   1001                 try:
   1002                     with st.spinner('저장...'): save_range_batch([n.strip() for n in names_str.split('\n') if n.strip()], rng[0], rng[-1], typ, sft, nte)
   1003                     st.success("완료"); st.rerun()
   1004                 except: st.error("오류")
   1005     with t2:
   1006         ed = st.date_input("행사 기간", [], key="evt_rng")
   1007         et = st.text_input("내용", key="evt_tit")
   1008         if st.button("행사 저장"):
   1009             if et and len(ed) > 0:
   1010                 for d in pd.date_range(ed[0], ed[-1]): add_company_event(d.strftime("%Y-%m-%d"), et)
   1011                 st.cache_data.clear(); st.success("저장됨"); st.rerun()
   1012     with t3:
   1013         st.info("💡 여러 개의 엑셀 파일을 한 번에 업로드하면 근무 이력을 자동 분석하여 DB에 저장합니다.")
   1014         up_files = st.file_uploader("배차일지 엑셀 파일 (.xlsx)", type=['xlsx'], accept_multiple_files=True)
   1015         if up_files:
   1016             if st.button("분석 및 DB 저장 실행", type="primary"):
   1017                 with st.spinner(f"{len(up_files)}개 파일 분석 중... (시간이 조금 걸립니다)"):
   1018                     try:
   1019                         all_dfs = []
   1020                         for up_file in up_files:
   1021                             df_res = parse_roster_excel(up_file)
   1022                             all_dfs.append(df_res)
   1023
   1024                         if all_dfs:
   1025                             final_df = pd.concat(all_dfs, ignore_index=True)
   1026                             cnt = save_work_history(final_df)
   1027                             st.success(f"✅ {len(up_files)}개 파일에서 총 {cnt}건의 신규 근무 이력이 저장/갱신되었습니다!")
   1028                         else:
   1029                             st.warning("분석할 데이터가 없습니다.")
   1030
   1031                     except Exception as e:
   1032                         st.error(f"실패: {e}")
   1033                         st.code(traceback.format_exc())
   1034     with t4:
   1035         st.write("### 🛑 운행 감축(Reduction) 규칙 설정")
   1036         c_r1, c_r2 = st.columns(2)
   1037         with c_r1:
   1038             g_start = st.date_input("시작일", value=datetime(2025,1,1))
   1039             g_end = st.date_input("종료일", value=datetime(2025,12,31))
   1040         with c_r2:
   1041             g_route = st.text_input("노선 번호 (예: 211)")
   1042             g_seq = st.text_input("순번 (예: 3)")
   1043             g_cond = st.selectbox("적용 조건", ["Weekend/Holiday", "Always"])
   1044
   1045         if st.button("규칙 추가"):
   1046             if g_route and g_seq:
   1047                 add_reduction_rule(g_start, g_end, g_route, g_seq, g_cond)
   1048                 st.success("규칙 추가됨"); st.rerun()
   1049
   1050         st.divider()
   1051         try:
   1052             rules_df = load_data("reduction_rules")
   1053             if not rules_df.empty: st.dataframe(rules_df)
   1054         except: st.caption("등록된 규칙 없음")
   1055
   1056 def render_driver_manage_tab():
   1057     st.subheader("⚙️ 승무원 및 조(Group) 관리")
   1058     tab_bulk, tab_change, tab_resign, tab_users = st.tabs(["➕ 승무원 등록", "🔄 조 변경", "👋 퇴사 처리", "🔐 관리자 계정"])
   1059     with tab_bulk:
   1060         c1, c2 = st.columns([3, 1])
   1061         with c1: bulk_names = st.text_area("승무원 성명 목록 (엑셀 붙여넣기)", height=150)
   1062         with c2:
   1063             selected_group = st.selectbox("소속 조", ["1조", "2조", "3조", "4조", "5조", "6조", "7조", "8조", "9조", "10조", "기타"])
   1064             st.markdown("<br>", unsafe_allow_html=True)
   1065             start_date = st.date_input("조 배정 시작일", get_kst_now().date())
   1066             st.markdown('<div class="red-button">', unsafe_allow_html=True)
   1067             if st.button("등록 실행", type="primary"):
   1068                 if bulk_names:
   1069                     names = [n.strip() for n in bulk_names.replace(',', '\n').split('\n') if n.strip()]
   1070                     cnt = 0
   1071                     for name in names:
   1072                         if ',' in name or '\t' in name: parts = name.replace('\t', ',').split(','); name = parts[0].strip()
   1073                         if add_driver_with_group(name, selected_group, start_date.strftime("%Y-%m-%d")): cnt += 1
   1074                     st.success(f"{cnt}명 등록 완료!"); st.rerun()
   1075             st.markdown('</div>', unsafe_allow_html=True)
   1076     with tab_change:
   1077         st.info("💡 엑셀 등에서 이름을 복사해 붙여넣고, 변경할 조와 날짜를 선택하면 일괄 변경됩니다.")
   1078         c1, c2 = st.columns([3, 1])
   1079         with c1:
   1080             change_names_str = st.text_area("대상 승무원 목록 (엔터로 구분)", height=200, key="change_names_input", placeholder="홍길동\n김철수\n이영희")
   1081         with c2:
   1082             target_grp = st.selectbox("이동할 조", ["1조", "2조", "3조", "4조", "5조", "6조", "7조", "8조", "9조", "10조", "기타"], key="new_grp_bulk")
   1083             st.markdown("<br>", unsafe_allow_html=True)
   1084             change_date = st.date_input("변경 기준일", get_kst_now().date(), key="eff_date_bulk")
   1085             st.markdown('<div class="red-button">', unsafe_allow_html=True)
   1086             if st.button("일괄 변경 적용", type="primary"):
   1087                 if change_names_str:
   1088                     names_to_change = [n.strip() for n in change_names_str.replace(',', '\n').split('\n') if n.strip()]
   1089                     all_drivers = load_data("drivers")
   1090                     all_db_names = all_drivers['name'].astype(str).tolist() if not all_drivers.empty else []
   1091                     valid_names = []
   1092                     invalid_names = []
   1093                     for name in names_to_change:
   1094                         if name in all_db_names: valid_names.append(name)
   1095                         else: invalid_names.append(name)
   1096                     if invalid_names: st.error(f"❌ 다음 이름은 명단에 없어 제외됩니다: {', '.join(invalid_names)}")
   1097                     if valid_names:
   1098                         success_cnt = 0
   1099                         for name in valid_names:
   1100                             if add_driver_with_group(name, target_grp, change_date.strftime("%Y-%m-%d")): success_cnt += 1
   1101                         st.success(f"✅ {success_cnt}명의 조를 '{target_grp}'로 변경했습니다.")
   1102                         if success_cnt > 0: st.balloons()
   1103                     else: st.warning("변경할 유효한 대상이 없습니다.")
   1104                 else: st.warning("이름을 입력해주세요.")
   1105             st.markdown('</div>', unsafe_allow_html=True)
   1106     with tab_resign:
   1107         drivers = load_data("drivers")
   1108         if not drivers.empty and 'resigned_date' in drivers.columns:
   1109             active_drivers = drivers[drivers['resigned_date'] == ""]
   1110         else:
   1111             active_drivers = pd.DataFrame()
   1112         if not active_drivers.empty:
   1113             st.info("💡 퇴사 처리를 하면 해당 날짜부터 근무 인원 집계 및 달력 표시에서 제외됩니다.")
   1114             c_r1, c_r2 = st.columns(2)
   1115             with c_r1: r_target = st.selectbox("퇴사자 선택", active_drivers['name'].tolist(), key="resign_dr")
   1116             with c_r2: r_date = st.date_input("퇴사 일자", get_kst_now().date(), key="resign_date")
   1117             st.markdown('<div class="red-button">', unsafe_allow_html=True)
   1118             if st.button("퇴사 처리 실행", type="primary", key="btn_resign"):
   1119                 set_driver_resignation(r_target, r_date.strftime("%Y-%m-%d"))
   1120                 st.success(f"{r_target}님 퇴사 처리 완료"); st.rerun()
   1121             st.markdown('</div>', unsafe_allow_html=True)
   1122         else: st.info("등록된 승무원이 없습니다.")
   1123     with tab_users:
   1124         st.write("### 🔐 관리자 및 직원 계정 관리")
   1125         c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
   1126         with c1: new_id = st.text_input("새 아이디")
   1127         with c2: new_pw = st.text_input("새 비밀번호", type="password")
   1128         with c3: new_role = st.selectbox("권한", ["admin", "staff"], format_func=lambda x: "관리자" if x == "admin" else "직원")
   1129         with c3: new_name = st.text_input("사용자 이름")
   1130         with c4:
   1131             st.markdown("<br>", unsafe_allow_html=True)
   1132             if st.button("계정 생성", type="primary"):
   1133                 if new_id and new_pw and new_name:
   1134                     if add_user_account(new_id, new_pw, new_role, new_name):
   1135                         st.success(f"계정 {new_id} 생성 완료"); st.rerun()
   1136                     else: st.error("이미 존재하는 아이디입니다.")
   1137                 else: st.warning("모든 항목을 입력하세요.")
   1138         st.divider()
   1139         st.write("### 🔑 비밀번호 변경")
   1140         users_df = load_data("users")
   1141         if not users_df.empty:
   1142             c_pw1, c_pw2, c_pw3 = st.columns([3, 3, 1])
   1143             with c_pw1: target_user_pw = st.selectbox("대상 계정 선택", users_df['username'].tolist())
   1144             with c_pw2: target_new_pw = st.text_input("변경할 비밀번호", type="password", key="chg_pw_input")
   1145             with c_pw3:
   1146                 st.markdown("<br>", unsafe_allow_html=True)
   1147                 if st.button("비밀번호 변경", type="primary"):
   1148                     if target_new_pw:
   1149                         if update_user_password(target_user_pw, target_new_pw):
   1150                             st.success(f"{target_user_pw}님의 비밀번호가 변경되었습니다.")
   1151                         else: st.error("변경 실패")
   1152                     else: st.warning("새 비밀번호를 입력하세요.")
   1153         st.divider()
   1154         st.write("📋 **등록된 계정 목록**")
   1155         if not users_df.empty:
   1156             for idx, row in users_df.iterrows():
   1157                 cc1, cc2, cc3, cc4, cc5 = st.columns([2, 2, 2, 2, 1])
   1158                 with cc1: st.write(f"**{row['username']}**")
   1159                 with cc2: st.write(row['name'])
   1160                 with cc3: st.write("관리자" if row['role']=='admin' else "직원")
   1161                 with cc4: st.write(row['created_at'])
   1162                 with cc5:
   1163                     if row['username'] != 'admin':
   1164                         if st.button("삭제", key=f"del_user_{row['username']}_{idx}"):
   1165                             delete_user_account(row['username'])
   1166                             st.success("삭제됨"); st.rerun()
   1167     st.divider()
   1168     drivers = load_data("drivers")
   1169     if not drivers.empty:
   1170         search_dr = st.text_input("승무원 명부 검색")
   1171         if search_dr and 'name' in drivers.columns:
   1172             drivers = drivers[drivers['name'].str.contains(search_dr)]
   1173         if 'resigned_date' in drivers.columns:
   1174             drivers['status'] = drivers['resigned_date'].apply(lambda x: f"퇴사 ({x})" if x else "재직")
   1175             st.dataframe(drivers[['name', 'group_name', 'status']], hide_index=True, use_container_width=True, height=800)
   1176         else:
   1177             st.dataframe(drivers, use_container_width=True)
   1178         with st.expander("🗑️ 승무원 삭제"):
   1179             if 'name' in drivers.columns:
   1180                 del_target = st.selectbox("삭제 대상", drivers['name'].tolist(), key="del")
   1181                 if st.button("영구 삭제"):
   1182                     delete_driver(del_target)
   1183                     st.rerun()
   1184
   1185 def render_individual_calendar_tab():
   1186     st.subheader("👤 승무원별 월간 근무 현황 (통합)")
   1187     inject_custom_css()
   1188     drivers = load_data("drivers")
   1189     if drivers.empty: st.warning("승무원 없음"); return
   1190
   1191     # [핵심 수정] 스케쥴 데이터 불러오기 및 정제 (날짜 형식 통일)
   1192     df_plan = load_data("schedules")
   1193
   1194     # 데이터가 있다면 컬럼 이름 공백 제거 및 날짜/이름 정규화
   1195     if not df_plan.empty:
   1196         df_plan.columns = df_plan.columns.str.strip() # 컬럼명 공백 제거
   1197
   1198         if 'date' in df_plan.columns:
   1199             # 날짜를 표준 형식 YYYY-MM-DD로 변환 (2025-1-1 등 비표준 형식 대응)
   1200             df_plan['date'] = pd.to_datetime(df_plan['date'], errors='coerce').dt.strftime("%Y-%m-%d")
   1201
   1202         if 'name' in df_plan.columns:
   1203             # 이름 앞뒤 공백 제거
   1204             df_plan['name'] = df_plan['name'].astype(str).str.strip()
   1205
   1206     # 데이터가 없거나 필수 컬럼이 없는 경우 빈 프레임 생성
   1207     if df_plan.empty or 'date' not in df_plan.columns:
   1208         df_plan = pd.DataFrame(columns=['date', 'name', 'type', 'note'])
   1209
   1210     df_work = load_data("work_history")
   1211     required_cols = ['date', 'name', 'shift', 'route', 'seq', 'car', 'is_sub']
   1212     if df_work.empty:
   1213         df_work = pd.DataFrame(columns=required_cols)
   1214     else:
   1215         for c in required_cols:
   1216             if c not in df_work.columns: df_work[c] = ""
   1217
   1218     now = get_kst_now()
   1219
   1220     # [수정] 초기화 로직 강화 (세션 스테이트가 없을 때만 오늘 날짜 대입)
   1221     if 'indiv_view_year' not in st.session_state:
   1222         st.session_state.indiv_view_year = now.year
   1223         st.session_state.sb_ind_year = now.year
   1224     if 'indiv_view_month' not in st.session_state:
   1225         st.session_state.indiv_view_month = now.month
   1226         st.session_state.sb_ind_month = now.month
   1227
   1228     # [수정] 1줄 정렬 UI (라벨 숨김 + 텍스트 컬럼 이용) - 개인별
   1229     c_nm, c_yr_txt, c_yr, c_mo_txt, c_mo, c_prev, c_next = st.columns([2, 0.4, 0.8, 0.3, 0.7, 0.4, 0.4])
   1230
   1231     with c_nm: target = st.selectbox("승무원 선택", drivers['name'].tolist(), key='sel_driver', label_visibility="collapsed")
   1232     with c_yr_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>년도:</div>", unsafe_allow_html=True)
   1233     with c_yr:
   1234         # [핵심] Selectbox 값과 indiv_view_year 동기화
   1235         year_range_ind = range(2023, now.year + 3)
   1236         selected_year = st.selectbox("년도", year_range_ind, index=year_range_ind.index(st.session_state.indiv_view_year), key='sb_ind_year', label_visibility="collapsed")
   1237         if selected_year != st.session_state.indiv_view_year:
   1238             st.session_state.indiv_view_year = selected_year
   1239             st.rerun()
   1240
   1241     with c_mo_txt: st.markdown("<div style='padding-top:10px; font-weight:bold; text-align:right;'>월:</div>", unsafe_allow_html=True)
   1242     with c_mo:
   1243         # [핵심] Selectbox 값과 indiv_view_month 동기화
   1244         month_range_ind = range(1, 13)
   1245         selected_month = st.selectbox("월", month_range_ind, index=month_range_ind.index(st.session_state.indiv_view_month), key='sb_ind_month', label_visibility="collapsed")
   1246         if selected_month != st.session_state.indiv_view_month:
   1247             st.session_state.indiv_view_month = selected_month
   1248             st.rerun()
   1249
   1250     with c_prev:
   1251         st.button("◀", key="i_prev_btn", on_click=prev_month_indiv)
   1252
   1253     with c_next:
   1254         st.button("▶", key="i_next_btn", on_click=next_month_indiv)
   1255
   1256     st.divider()
   1257
   1258     if target:
   1259         year, month = st.session_state.indiv_view_year, st.session_state.indiv_view_month
   1260         filter_ym = f"{year}-{month:02d}"
   1261
   1262         # [확인] 날짜 컬럼 형식 통일로 인해 startstartswith가 정상 작동함
   1263         my_plan = df_plan[(df_plan['name']==target) & (df_plan['date'].astype(str).str.startswith(filter_ym))] if not df_plan.empty else pd.DataFrame()
   1264         my_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(filter_ym))] if not df_work.empty else pd.DataFrame()
   1265
   1266         # [수정] 통계 계산 로직 (월간/연간)
   1267         if not my_work.empty and 'shift' in my_work.columns:
   1268             stats_am = len(my_work[my_work['shift'] == '오전'])
   1269             stats_pm = len(my_work[my_work['shift'] == '오후'])
   1270         else:
   1271             stats_am, stats_pm = 0, 0
   1272
   1273         # 연간 통계
   1274         y_filter = f"{year}-"
   1275         y_work = df_work[(df_work['name']==target) & (df_work['date'].astype(str).str.startswith(y_filter))] if not df_work.empty else pd.DataFrame()
   1276         if not y_work.empty and 'shift' in y_work.columns:
   1277             y_am = len(y_work[y_work['shift'] == '오전'])
   1278             y_pm = len(y_work[y_work['shift'] == '오후'])
   1279         else:
   1280             y_am, y_pm = 0, 0
   1281
   1282         # 상단 통계 배지
   1283         st.markdown(f"""
   1284         <div style='display:flex; justify-content:center; gap:20px; margin-bottom:15px;'>
   1285             <div style='background:#E3F2FD; padding:10px 20px; border-radius:10px; text-align:center; border:1px solid #90CAF9;'>
   1286                 <div style='font-size:12px; font-weight:bold; color:#1565C0;'>📅 {month}월 근무</div>
   1287                 <div style='font-size:14px;'>오전 <span style='color:blue; font-weight:bold;'>{stats_am}</span> / 오후 <span style='color:red; font-weight:bold;'>{stats_pm}</span></div>
   1288             </div>
   1289             <div style='background:#FFF3E0; padding:10px 20px; border-radius:10px; text-align:center; border:1px solid #FFCC80;'>
   1290                 <div style='font-size:12px; font-weight:bold; color:#E65100;'>📈 {year}년 누적</div>
   1291                 <div style='font-size:14px;'>오전 <span style='color:blue; font-weight:bold;'>{y_am}</span> / 오후 <span style='color:red; font-weight:bold;'>{y_pm}</span></div>
   1292             </div>
   1293         </div>
   1294         """, unsafe_allow_html=True)
   1295
   1296         gh = load_data("group_history")
   1297         h_dict = {}
   1298         if not gh.empty:
   1299             for _, r in gh.iterrows():
   1300                 if r['driver_name'] not in h_dict: h_dict[r['driver_name']] = []
   1301                 h_dict[r['driver_name']].append((r['start_date'], r['group_name']))
   1302             for k in h_dict: h_dict[k].sort(key=lambda x:x[0], reverse=True)
   1303
   1304         cols = st.columns(7)
   1305         for w in WEEKDAY_KOREAN: cols[WEEKDAY_KOREAN.index(w)].markdown(f"<div style='text-align:center; font-weight:bold;'>{w}</div>", unsafe_allow_html=True)
   1306
   1307         for week in calendar.monthcalendar(year, month):
   1308             cols = st.columns(7)
   1309             for i, day in enumerate(week):
   1310                 with cols[i]:
   1311                     if day == 0: st.write("")
   1312                     else:
   1313                         d_str = f"{year}-{month:02d}-{day:02d}"
   1314                         grp = get_group_from_dict(h_dict, target, d_str)
   1315                         auto = calculate_auto_shift(grp, d_str)
   1316
   1317                         cell_bg = "transparent"
   1318                         txt = ""
   1319
   1320                         p_work = my_work[my_work['date'] == d_str] if not my_work.empty else pd.DataFrame()
   1321                         p_plan = my_plan[my_plan['date'] == d_str] if not my_plan.empty else pd.DataFrame()
   1322
   1323                         if not p_work.empty:
   1324                             w_row = p_work.iloc[0]
   1325                             is_sub_str = str(w_row.get('is_sub', 'FALSE')).upper()
   1326                             is_sub = (is_sub_str == 'TRUE' or is_sub_str == 'Y')
   1327
   1328                             if w_row['shift'] == '감차휴무':
   1329                                 cell_bg = get_type_color('감차휴무')
   1330                                 txt = f"<span style='color:white; font-weight:bold;'>감차휴무</span><br><span style='font-size:9px; color:white; opacity:0.8;'>({w_row['route']}-{w_row['seq']})</span>"
   1331                             else:
   1332                                 if w_row['shift'] == '오전': cell_bg = get_type_color('실제근무_본인')
   1333                                 elif w_row['shift'] == '오후': cell_bg = "#e53935" # 진한 빨강
   1334                                 if is_sub: cell_bg = get_type_color('실제근무_대운')
   1335
   1336                                 txt = f"""<span style='color:white; font-weight:bold; font-size:11px;'>{w_row['route']} {w_row['seq']}번<br>({w_row['car']})</span><br>
   1337                                         <span style='font-size:12px; color:white; font-weight:bold;'>{w_row['shift']}</span>"""
   1338
   1339                         elif not p_plan.empty:
   1340                             pl_row = p_plan.iloc[0]
   1341                             t = pl_row['type']
   1342                             cell_bg = get_type_color(t)
   1343                             txt = f"<span style='color:white;'>{t}</span>"
   1344                         else:
   1345                             if auto == "오전": cell_bg="#e3f2fd"; txt=f"<span style='color:blue;'>오전 ({grp})</span>"
   1346                             elif auto == "오후": cell_bg="#fff3e0"; txt=f"<span style='color:red;'>오후 ({grp})</span>"
   1347                             elif auto == "휴무": cell_bg="#f1f3f5"; txt=f"<span style='color:#999;'>휴무 ({grp})</span>"
   1348
   1349                         st.markdown(f"""
   1350                         <div style='background-color:{cell_bg}; border:1px solid #ddd; border-radius:5px; min-height:80px; height:auto; padding:5px; display:flex; flex-direction:column;
        justify-content:center; align-items:center;'>
   1351                             <div style='font-weight:bold; font-size:14px; color:#333; margin-bottom:2px;'>{day}</div>
   1352                             <div style='text-align:center; font-size:12px; line-height:1.2;'>{txt}</div>
   1353                         </div>""", unsafe_allow_html=True)
   1354
   1355 def render_view_manage_tab():
   1356     st.subheader("📊 데이터 조회")
   1357     df = load_data("schedules")
   1358     if df.empty or 'date' not in df.columns:
   1359         st.info("데이터가 없습니다.")
   1360         return
   1361
   1362     with st.expander("검색"):
   1363         n = st.text_input("이름")
   1364         if n: st.dataframe(df[df['name'].str.contains(n)], use_container_width=True)
   1365         else: st.dataframe(df, use_container_width=True)
   1366
   1367 def render_public_search_tab(): render_view_manage_tab()
   1368
   1369 def main():
   1370     st.set_page_config(page_title="우진교통 배차 관리 시스템", layout="wide")
   1371     inject_custom_css()
   1372     if 'auth_status' not in st.session_state: st.session_state['auth_status'] = None
   1373     if st.session_state['auth_status'] is None:
   1374         st.markdown("<br><br><br>", unsafe_allow_html=True)
   1375         c1, c2, c3 = st.columns([1, 1, 1])
   1376         with c2:
   1377             st.title("우진교통 배차 관리 시스템")
   1378             uid = st.text_input("아이디")
   1379             upw = st.text_input("비밀번호", type="password")
   1380             st.markdown('<div class="login-btn">', unsafe_allow_html=True)
   1381             if st.button("로그인", type="primary", use_container_width=True):
   1382                 user = login_user(uid, upw)
   1383                 if user:
   1384                     st.session_state['auth_status'] = user[0]
   1385                     st.session_state['user_name'] = user[1]
   1386                     log_login_access(uid, user[1])
   1387                     st.rerun()
   1388                 else: st.error("로그인 실패")
   1389             st.markdown('</div>', unsafe_allow_html=True)
   1390         return
   1391
   1392     # [수정] 로그아웃 버튼 우측 상단 배치
   1393     c_head1, c_head2 = st.columns([8, 1])
   1394     with c_head1: st.title(f"우진교통 배차 관리 시스템 ({st.session_state.get('user_name')}님)")
   1395     with c_head2:
   1396         if st.button("로그아웃"): st.session_state['auth_status']=None; st.rerun()
   1397
   1398     if st.session_state['auth_status'] == 'admin':
   1399         t1, t2, t3, t4, t5, t6 = st.tabs(["📅 전체 현황", "👤 개인별", "📝 입력/배차", "⚙️ 승무원", "📊 조회", "🔧 로그"])
   1400         with t1: render_calendar_tab()
   1401         with t2: render_individual_calendar_tab()
   1402         with t3: render_input_tab()
   1403         with t4: render_driver_manage_tab()
   1404         with t5: render_view_manage_tab()
   1405         with t6: render_log_tab()
   1406     else:
   1407         t1, t2, t3 = st.tabs(["📅 전체 현황", "👤 개인별", "📊 조회"])
   1408         with t1: render_calendar_tab()
   1409         with t2: render_individual_calendar_tab()
   1410         with t3: render_public_search_tab()
   1411
   1412 if __name__ == '__main__':
   1413     main()
