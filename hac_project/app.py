import streamlit as st

from ui import tab_input, tab_result, tab_proof, tab_sizing, tab_attribute_summary, tab_sld, tab_svg


# WELCOME P.FILM
# เป็นระบบคำนวนทั้ง2source และ 4source
st.set_page_config(page_title="HAC Load Designer", layout="wide")

st.title("⚡ DATA HALL DISTRIBUTION DESIGNER")

tab_1, tab_2, tab_3, tab_4, tab_5, tab_6, tab_7 = st.tabs(
    ["📋 กรอกข้อมูล", "📊 ผลลัพธ์", "🔍 Optimization Proof", "⚙️ Equipment Sizing",
     "🧮 Attribute Calculation", "📐 SLD Attributes", "🌀 SVG Sizing"]
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
    tab_attribute_summary.render()

with tab_6:
    tab_sld.render()

with tab_7:
    tab_svg.render()

