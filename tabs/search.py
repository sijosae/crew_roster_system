import streamlit as st
import utils

def render_view_manage_tab():
    st.subheader("📊 데이터 조회")
    df = utils.load_data("schedules")
    if df.empty or 'date' not in df.columns:
        st.info("데이터가 없습니다.")
        return

    with st.expander("검색"):
        n = st.text_input("이름")
        if n: st.dataframe(df[df['name'].str.contains(n)], use_container_width=True)
        else: st.dataframe(df, use_container_width=True)

def render_public_search_tab():
    render_view_manage_tab()
