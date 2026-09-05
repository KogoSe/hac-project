import streamlit as st

from ui import tab_input, tab_result, tab_proof, tab_sizing, tab_sld

# เป็นระบบคำนวนทั้ง2source และ 4source
st.set_page_config(page_title="HAC Load Designer", layout="wide")

st.title("⚡ DATA HALL DISTRIBUTION DESIGNER")

tab_1, tab_2, tab_3, tab_4, tab_5 = st.tabs(
    ["📋 กรอกข้อมูล", "📊 ผลลัพธ์", "🔍 Optimization Proof", "⚙️ Equipment Sizing", "📐 SLD Attributes"]
)

with tab_1:
    tab_input.render()

with tab_2:
    tab_result.render()

with tab_3:
    tab_proof.render()

with tab_4:
    tab_sizing.render()

with tab_5:
    tab_sld.render()
