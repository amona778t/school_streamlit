# app.py (최종 통합 버전 — 복사해서 덮어쓰기)
import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, timedelta, date

# ---------------- constants ----------------
USERS_CSV = "users.csv"
SCHEDULES_CSV = "schedules.csv"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_SECRET_KEY = "ADMINKY2025"  # 관리자 로그인 시 추가 인증코드

# ---------------- safe rerun util ----------------
def safe_rerun():
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
            return
        except Exception:
            pass
    if hasattr(st, "rerun"):
        try:
            st.rerun()
            return
        except Exception:
            pass
    st.stop()

# ---------------- ensure files ----------------
def ensure_files():
    if not os.path.exists(USERS_CSV):
        users = pd.DataFrame(columns=["username","password","role","teacher_name"])
        users.loc[len(users)] = [ADMIN_USERNAME, ADMIN_PASSWORD, "관리자", ""]
        users.to_csv(USERS_CSV, index=False, encoding="utf-8-sig")
    if not os.path.exists(SCHEDULES_CSV):
        cols = ["id","username","role","title","description","date","shared","creator_display","checked_at","done","created_at"]
        pd.DataFrame(columns=cols).to_csv(SCHEDULES_CSV, index=False, encoding="utf-8-sig")

ensure_files()

# ---------------- IO helpers ----------------
def _to_dt_safe(s):
    return pd.to_datetime(s, errors="coerce")

def load_users():
    # 항상 UTF-8-SIG 로 읽기
    df = pd.read_csv(USERS_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    if "teacher_name" not in df.columns:
        df["teacher_name"] = ""
    return df

def save_users(df):
    df.to_csv(USERS_CSV, index=False, encoding="utf-8-sig")

def load_schedules():
    # 일정 파일도 UTF-8-SIG 로 통일
    df = pd.read_csv(SCHEDULES_CSV, encoding="utf-8-sig").fillna("")
    cols = ["id","username","role","title","description","date","shared","creator_display","checked_at","done","created_at"]
    for c in cols:
        if c not in df.columns:
            df[c] = "" if c not in ["shared","done"] else False

    if df.shape[0] == 0:
        empty = pd.DataFrame(columns=cols)
        empty["shared"] = empty["shared"].astype(bool)
        empty["done"] = empty["done"].astype(bool)
        return empty

    df["date"] = _to_dt_safe(df["date"])
    df["checked_at"] = _to_dt_safe(df["checked_at"])
    df["created_at"] = _to_dt_safe(df["created_at"])

    df["shared"] = df["shared"].astype(bool)
    df["done"] = df["done"].astype(bool)

    try:
        df["id"] = df["id"].astype(int)
    except:
        df = df.reset_index(drop=True)
        df["id"] = range(1, len(df) + 1)

    # 자동 완료 처리 (24시간 지나면 완료됨)
    now = datetime.now()
    mask = df["checked_at"].notna() & ((now - df["checked_at"]) >= timedelta(hours=24))
    df.loc[mask, "done"] = True

    return df

def save_schedules(df):
    df2 = df.copy()
    df2["date"] = df2["date"].apply(lambda x: x.isoformat() if pd.notna(x) else "")
    df2["checked_at"] = df2["checked_at"].apply(lambda x: x.isoformat() if pd.notna(x) else "")
    df2["created_at"] = df2["created_at"].apply(lambda x: x.isoformat() if pd.notna(x) else "")
    df2.to_csv(SCHEDULES_CSV, index=False, encoding="utf-8-sig")
# ---------------- auth ----------------
def register_user(username, password, role, teacher_name=""):
    users = load_users()
    username = (username or "").strip()
    if not username or not password:
        return False, "아이디와 비밀번호를 입력하세요."
    if username in users["username"].values:
        return False, "이미 존재하는 아이디입니다."
    if role not in ["학생","선생님"]:
        return False, "가입은 학생 또는 선생님만 가능합니다."
    new = {"username": username, "password": password, "role": role, "teacher_name": teacher_name}
    users = pd.concat([users, pd.DataFrame([new])], ignore_index=True)
    save_users(users)
    return True, "회원가입 성공했습니다. 로그인 해주세요."

def authenticate(username, password, role, admin_secret=""):
    users = load_users()
    username = (username or "").strip()
    password = (password or "")
    if role == "관리자":
        if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
            return None, "관리자 아이디/비밀번호 불일치."
        if admin_secret != ADMIN_SECRET_KEY:
            return None, "관리자 비밀코드가 올바르지 않습니다."
        row = users[(users["username"]==ADMIN_USERNAME)&(users["role"]=="관리자")]
        if row.empty:
            return None, "관리자 계정이 없습니다."
        return row.iloc[0].to_dict(), ""
    else:
        row = users[(users["username"]==username)&(users["password"]==password)&(users["role"]==role)]
        if row.empty:
            return None, "아이디/비밀번호/역할을 확인하세요."
        return row.iloc[0].to_dict(), ""

# ---------------- schedule ops ----------------
def get_next_id(df):
    if df is None or df.empty:
        return 1
    return int(df["id"].max()) + 1

def add_schedule(username, role, title, description, date_value, shared, creator_display):
    df = load_schedules()
    title_s = (title or "").strip()
    if title_s == "":
        return False, "제목을 입력하세요."

    # 날짜 변환 (사용자가 선택한 date_input 값 → datetime)
    date_norm = pd.to_datetime(date_value).normalize()

    # df["date"]를 안전하게 datetime으로 변환 (문자열로 저장된 경우 대비)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # 중복 일정 방지: 같은 제목 + 같은 날짜 + 같은 등록자
    dup = df[
        (df["title"].str.strip().str.lower() == title_s.lower()) &
        (df["date"].notna()) &
        (df["date"].dt.normalize() == date_norm) &
        (df["creator_display"].fillna("") == creator_display)
    ]
    if not dup.empty:
        return False, "같은 제목·같은 날짜·같은 등록자로 이미 등록된 일정이 있습니다."

    nid = get_next_id(df)
    new = {
        "id": nid,
        "username": username,
        "role": role,
        "title": title_s,
        "description": (description or "").strip(),
        "date": date_norm,
        "shared": bool(shared),
        "creator_display": creator_display,
        "checked_at": pd.NaT,
        "done": False,
        "created_at": datetime.now()
    }
    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    save_schedules(df)
    return True, "일정 등록 완료."

# -- 새로 추가: 수정 / 삭제 함수 (원본 구조에 맞게 최소 변경) --
def update_schedule(item_id, new_title, new_desc, new_date, new_shared):
    if (new_title or "").strip() == "":
        return False, "제목을 입력하세요."
    df = load_schedules()
    idxs = df.index[df["id"] == item_id].tolist()
    if not idxs:
        return False, "일정을 찾을 수 없습니다."
    i = idxs[0]
    df.at[i, "title"] = (new_title or "").strip()
    df.at[i, "description"] = (new_desc or "").strip()
    try:
        df.at[i, "date"] = pd.to_datetime(new_date)
    except Exception:
        df.at[i, "date"] = pd.NaT
    df.at[i, "shared"] = bool(new_shared)
    save_schedules(df)
    return True, "일정이 수정되었습니다."

def delete_schedule(item_id):
    df = load_schedules()
    if df.empty:
        return False, "삭제할 일정이 없습니다."
    if item_id not in df["id"].values:
        return False, "일정을 찾을 수 없습니다."
    df2 = df[df["id"] != item_id].reset_index(drop=True)
    # (선택적으로 id 재정렬하지 않음 — 원하면 재정렬 가능)
    save_schedules(df2)
    return True, "일정이 삭제되었습니다."

def toggle_checked_and_sync(item_id: int, new_value: bool):
    """Direct toggle utility (used when we programmatically toggle). Updates CSV and syncs session keys."""
    df = load_schedules()
    idxs = df.index[df["id"]==item_id].tolist()
    if not idxs:
        return
    i = idxs[0]
    if new_value:
        df.at[i, "checked_at"] = datetime.now()
    else:
        df.at[i, "checked_at"] = pd.NaT
        df.at[i, "done"] = False
    save_schedules(df)
    # update all related session_state checkbox keys for this id so UI syncs
    k_list = [f"chk_{item_id}", f"detail_chk_{item_id}"]
    for k in k_list:
        st.session_state[k] = new_value
    # immediate refresh

def toggle_checked_by_key(item_id, state_key):
    """Callback for checkbox on_change: read session_state[state_key] and apply."""
    val = st.session_state.get(state_key, False)
    # call central toggle
    toggle_checked_and_sync(item_id, val)

# ---------------- display utils ----------------
def ellipsis(text, n=15):
    t = (text or "")
    return t if len(t) <= n else t[:n] + "..."

def style_for_row(r):
    # 유저별 체크 상태 CSV
    USER_STATUS_CSV = "user_schedule_status.csv"
    if not os.path.exists(USER_STATUS_CSV):
        return ""  # 체크기록 자체가 없으면 기본 표시

    status_df = pd.read_csv(USER_STATUS_CSV, dtype=str).fillna("")

    # 현재 로그인한 유저가 이 일정 체크한 기록 찾기
    row = status_df[
        (status_df["username"] == st.session_state.username) &
        (status_df["schedule_id"] == str(r["id"]))
    ]

    # 체크한 기록이 있고 checked_at 값이 있으면 줄긋기
    if not row.empty and row["checked_at"].iloc[0] != "":
        return "color:gray; text-decoration: line-through;"

    # 체크 안했으면 기본 스타일
    return ""

# ---------------- session init ----------------
def init_session():
    st.set_page_config(page_title="학사일정 관리", layout="wide")
    defaults = {
        "page": "auth",
        "username": None,
        "role": None,
        "teacher_name": "",
        "selected_id": None,
        "cal_year": date.today().year,
        "cal_month": date.today().month
    }
    for k,v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ---------------- PAGE: Auth ----------------
def page_auth():
    st.title("🔐 일정 관리 프로그램")
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        tabs = st.tabs(["로그인","회원가입"])
        with tabs[0]:
            with st.form("login_form", clear_on_submit=False):
                uname = st.text_input("아이디")
                pwd = st.text_input("비밀번호", type="password")
                role = st.selectbox("역할", ["학생","선생님","관리자"])
                admin_secret = ""
                if role == "관리자":
                    admin_secret = st.text_input("관리자 비밀코드", type="password", help="관리자 접근용 비밀코드 필요")
                submitted = st.form_submit_button("로그인")
            if submitted:
                user, err = authenticate(uname, pwd, role, admin_secret)
                if user:
                    st.session_state.username = user["username"]
                    st.session_state.role = user["role"]
                    st.session_state.teacher_name = user.get("teacher_name","")
                    st.session_state.page = "main"
                    st.success("로그인 성공 — 이동합니다.")
                    safe_rerun()
                else:
                    st.error(err)
        with tabs[1]:

            # ✅ 역할 선택은 form 바깥에서 먼저 수행 (즉시 반영 위해)
            new_role = st.selectbox("가입 역할", ["학생", "선생님"])

            with st.form("signup_form", clear_on_submit=True):
                new_u = st.text_input("새 아이디")
                new_p = st.text_input("새 비밀번호", type="password")

                # ✅ 선생님 선택 시에만 입력창 표시 (즉시 반영됨)
                if new_role == "선생님":
                    tname = st.text_input("선생님 이름 (달력에 표시될 이름)")
                else:
                    tname = ""

                reg = st.form_submit_button("회원가입")

            if reg:
                ok, msg = register_user(new_u, new_p, new_role, tname)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
# ---------------- PAGE: Main ----------------
def page_main():
    # Sidebar
    with st.sidebar:
        st.write(f"👤 {st.session_state.username} ({st.session_state.role})")
        menu = ["일정 등록","전체 일정 보기","달력 보기"]
        if st.session_state.role == "관리자":
            menu.append("관리자")
        choice = st.radio("메뉴 선택", menu, index=0)
        if st.button("로그아웃"):
            # immediate logout
            st.session_state.page = "auth"
            st.session_state.username = None
            st.session_state.role = None
            st.session_state.teacher_name = ""
            st.session_state.selected_id = None
            safe_rerun()

    # ---------- 일정 등록 ----------
    if choice == "일정 등록":
        st.header("📝 일정 등록")
        title = st.text_input("제목")
        desc = st.text_area("내용")
        dval = st.date_input("날짜", min_value=date.today())

        shared = False
        creator_display = st.session_state.username
        if st.session_state.role == "선생님":
            shared = st.checkbox("공유 일정으로 등록 (모두에게 표시)")
            if shared:
                creator_display = st.session_state.teacher_name or st.session_state.username
        else:
            shared = False

        if st.button("등록"):
            ok,msg = add_schedule(st.session_state.username, st.session_state.role, title, desc, dval, shared, creator_display)
            if ok:
                st.success(msg)
                safe_rerun()
            else:
                st.error(msg)

    # --- 메뉴 변경 시 상세보기/수정 상태 초기화 ---
    if "last_choice" not in st.session_state:
        st.session_state.last_choice = choice

    if st.session_state.last_choice != choice:
        st.session_state.selected_id = None
        st.session_state.edit_mode = False
        st.session_state.delete_confirm = False
        st.session_state.last_choice = choice

    # ---------- 전체 일정 보기 ----------
    if choice == "전체 일정 보기":
        st.header("📋 전체 일정 보기")
        df = load_schedules()
        if st.session_state.role in ["학생","선생님"]:
            df = df[(df["username"]==st.session_state.username) | (df["shared"]==True)]
        df = df.sort_values(["date","created_at"]).reset_index(drop=True)

        in_prog = df[df["done"]==False]
        done = df[df["done"]==True]

        st.subheader("⏳ 진행중")
        if in_prog.empty:
            st.info("진행중인 일정이 없습니다.")
        else:
            for _, r in in_prog.iterrows():
                USER_STATUS_CSV = "user_schedule_status.csv"
                if not os.path.exists(USER_STATUS_CSV):
                    pd.DataFrame(columns=["username","schedule_id","checked_at","done"]).to_csv(
                        USER_STATUS_CSV, index=False, encoding="utf-8-sig"
                    )

                status_df = pd.read_csv(USER_STATUS_CSV, dtype=str).fillna("")

                row = status_df[
                    (status_df["username"] == st.session_state.username) &
                    (status_df["schedule_id"] == str(r["id"]))
                ]

                initial_checked = False if row.empty else (row["checked_at"].iloc[0] != "")

                chk_key = f"chk_{st.session_state.username}_{r['id']}"

                if chk_key not in st.session_state:
                    st.session_state[chk_key] = initial_checked

                def toggle_check_user(schedule_id=r["id"], key=chk_key):
                    val = st.session_state[key]
                    status_df = pd.read_csv(USER_STATUS_CSV, dtype=str).fillna("")
                    row = status_df[
                        (status_df["username"] == st.session_state.username) &
                        (status_df["schedule_id"] == str(schedule_id))
                    ]

                    if val:
                        if row.empty:
                            new = pd.DataFrame([{
                                "username": st.session_state.username,
                                "schedule_id": str(schedule_id),
                                "checked_at": datetime.now(),
                                "done": ""
                            }])
                            status_df = pd.concat([status_df, new], ignore_index=True)
                        else:
                            status_df.loc[row.index[0], "checked_at"] = datetime.now()
                    else:
                        if not row.empty:
                            status_df.loc[row.index[0], "checked_at"] = ""
                            status_df.loc[row.index[0], "done"] = ""

                    status_df.to_csv(USER_STATUS_CSV, index=False, encoding="utf-8-sig")

                left, mid, right = st.columns([0.08, 0.72, 0.20])

                with left:
                    st.checkbox("", key=chk_key, on_change=toggle_check_user)

                style = style_for_row(r)
                title_disp = ellipsis(r["title"], 15)

                with mid:
                    st.markdown(
                        f"<div style='{style}'>{pd.to_datetime(r['date']).date()} | "
                        f"<b>{title_disp}</b> ({'공유' if r['shared'] else '개인'}) — {r['creator_display']}</div>",
                        unsafe_allow_html=True
                    )

                with right:
                    if st.button("상세", key=f"detail_{int(r['id'])}"):
                        st.session_state.selected_id = int(r['id'])
                        safe_rerun()

        st.subheader("✅ 완료된 일정 (체크 후 24시간 경과)")
        if done.empty:
            st.info("완료된 일정이 없습니다.")
        else:
            for _, r in done.iterrows():
                title_disp = ellipsis(r["title"], 15)
                st.markdown(f"<div style='color:gray; text-decoration: line-through;'>{pd.to_datetime(r['date']).date()} | {title_disp} ({'공유' if r['shared'] else '개인'}) — {r['creator_display']}</div>", unsafe_allow_html=True)

    # ---------- 상세보기 ----------
    if st.session_state.selected_id:
        df_all = load_schedules()
        sel = df_all[df_all["id"]==st.session_state.selected_id]

        if not sel.empty:
            r = sel.iloc[0]
            st.markdown("---")
            st.subheader("📌 일정 상세보기")

            # 수정 모드 여부
            if "edit_mode" not in st.session_state:
                st.session_state.edit_mode = False

            # 삭제 확인 모드 여부
            if "delete_confirm" not in st.session_state:
                st.session_state.delete_confirm = False

            if st.session_state.edit_mode:
                # --- 수정 모드 입력 UI ---
                new_title = st.text_input("제목", r["title"])
                new_desc = st.text_area("내용", r["description"])
                new_date = st.date_input("날짜", pd.to_datetime(r["date"]).date())

                if st.button("수정 완료"):
                    # 중복 검사
                    df_all["date"] = pd.to_datetime(df_all["date"], errors="coerce")
                    date_norm = pd.to_datetime(new_date).normalize()

                    dup = df_all[
                        (df_all["id"] != r["id"]) &
                        (df_all["title"].str.strip().str.lower() == new_title.strip().lower()) &
                        (df_all["date"].notna()) &
                        (df_all["date"].dt.normalize() == date_norm) &
                        (df_all["creator_display"] == r["creator_display"])
                    ]
                    if not dup.empty:
                        st.error("⚠️ 같은 제목·같은 날짜·같은 등록자로 이미 등록된 일정이 있습니다.")
                    else:
                        idx = df_all.index[df_all["id"] == r["id"]][0]
                        df_all.at[idx, "title"] = new_title.strip()
                        df_all.at[idx, "description"] = new_desc.strip()
                        df_all.at[idx, "date"] = date_norm
                        save_schedules(df_all)
                        st.success("✅ 일정 수정 완료!")
                        st.session_state.edit_mode = False
                        safe_rerun()

                if st.button("수정 취소"):
                    st.session_state.edit_mode = False
                    safe_rerun()

            else:
                # --- 상세 모드 표시 ---
                st.write(f"**제목:** {r['title']}")
                st.write(f"**내용:** {r['description']}")
                st.write(f"**날짜:** {pd.to_datetime(r['date']).date()}")
                st.write(f"**등록자:** {r['creator_display']}")
                st.write(f"**공유 여부:** {'공유' if r['shared'] else '개인'}")

                st.markdown("---")

                # ✅ 수정 가능 조건
                can_edit = (
                    (r["username"] == st.session_state.username)  # 본인이 만든 일정
                    or (st.session_state.role == "관리자")        # 관리자는 전체 수정 가능
                )

                if can_edit:
                    # ✏️ 본인 또는 관리자만 수정 가능
                    if st.button("수정", key=f"edit_{r['id']}"):
                        st.session_state.edit_mode = True
                        safe_rerun()

                    # ✅ 일정별 삭제 상태 key 생성
                    delete_key = f"delete_confirm_{int(r['id'])}"
                    if delete_key not in st.session_state:
                        st.session_state[delete_key] = False

                    if not st.session_state[delete_key]:
                        if st.button("삭제"):
                            st.session_state[delete_key] = True
                            safe_rerun()
                    else:
                        st.warning("정말 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("삭제 확정"):
                                df_all = df_all[df_all["id"] != r["id"]]
                                save_schedules(df_all)
                                st.success("🗑️ 삭제 완료!")
                                st.session_state.selected_id = None
                                st.session_state[delete_key] = False
                                safe_rerun()
                        with col2:
                            if st.button("삭제 취소"):
                                st.session_state[delete_key] = False
                                safe_rerun()

                else:
                    # 🔒 권한 없음 안내
                    st.info("🔒 이 일정은 작성자만 수정 또는 삭제할 수 있습니다.")

    # ---------- 달력 보기 ----------
    if choice == "달력 보기":
        st.header("📅 달력 보기")
        c1,c2,c3 = st.columns([1,2,1])
        with c1:
            if st.button("◀ 이전달"):
                if st.session_state.cal_month == 1:
                    st.session_state.cal_month = 12
                    st.session_state.cal_year -= 1
                else:
                    st.session_state.cal_month -= 1
                safe_rerun()
        with c3:
            if st.button("다음달 ▶"):
                if st.session_state.cal_month == 12:
                    st.session_state.cal_month = 1
                    st.session_state.cal_year += 1
                else:
                    st.session_state.cal_month += 1
                safe_rerun()
        with c2:
            st.markdown(f"<h4 style='text-align:center'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h4>", unsafe_allow_html=True)

        df = load_schedules()
        if st.session_state.role in ["학생","선생님"]:
            df = df[(df["username"]==st.session_state.username) | (df["shared"]==True)]

        st.markdown("""
        <style>
        table.calendar {border-collapse: collapse; width: 100%;}
        table.calendar th {border:1px solid #999; padding:6px; text-align:center; background:#f2f2f2;}
        table.calendar td {border:1px solid #999; width:14.28%; height:120px; vertical-align:top; padding:6px; font-size:12px; overflow:hidden;}
        .daynum {font-weight:bold; margin-bottom:6px;}
        .evt {font-size:11px; margin-bottom:4px; padding:3px; border-radius:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        </style>
        """, unsafe_allow_html=True)

        cal = calendar.Calendar(firstweekday=6)
        weeks = cal.monthdatescalendar(st.session_state.cal_year, st.session_state.cal_month)
        html = "<table class='calendar'><tr><th>일</th><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th><th>토</th></tr>"
        for week in weeks:
            html += "<tr>"
            for day in week:
                if day.month != st.session_state.cal_month:
                    html += "<td></td>"
                    continue
                if df.empty:
                    day_rows = pd.DataFrame(columns=df.columns)
                else:
                    day_rows = df[df["date"].notna() & (df["date"].dt.date == day)]
                cell_html = f"<div class='daynum'>{day.day}</div>"
                for _, r in day_rows.iterrows():
                    bg = "lightgreen" if r["shared"] else "lightblue"
                    style = ""
                    if pd.notna(r["checked_at"]) or r.get("done", False):
                        style = "text-decoration: line-through; color:gray;"
                        bg = "lightgray"
                    title = ellipsis(r["title"], 15)
                    cell_html += f"<div class='evt' style='background:{bg}; {style}' title='{r['title']}'>{title}</div>"
                html += f"<td>{cell_html}</td>"
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

    # ---------- 관리자 ----------
    if choice == "관리자" and st.session_state.role == "관리자":
        st.header("⚙ 관리자 페이지")
        st.subheader("사용자 목록")
        st.dataframe(load_users(), use_container_width=True)
        st.subheader("전체 일정")
        all_df = load_schedules().sort_values(["date","created_at"])
        st.dataframe(all_df, use_container_width=True)
        c1,c2 = st.columns(2)
        with c1:
            if st.button("모든 일정 초기화"):
                save_schedules(pd.DataFrame(columns=all_df.columns))
                st.success("모든 일정 초기화됨.")
                safe_rerun()
        with c2:
            if st.button("체크 표시 초기화"):
                all_df["checked_at"] = pd.NaT
                all_df["done"] = False
                save_schedules(all_df)
                st.info("모든 일정의 체크가 초기화되었습니다.")
                safe_rerun()

# ---------------- main entry ----------------
if st.session_state["page"] == "auth":
    page_auth()
else:
    page_main()