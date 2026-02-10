import streamlit as st
import io
import zipfile
import os

# 頁面設定 (must be the first streamlit command)
st.set_page_config(page_title="AI 批量去背縮放工具", layout="wide", initial_sidebar_state="expanded")

# Inject Custom CSS for Canvas Effect
st.markdown("""
<style>
    .stApp {
        background-color: #1e1e1e;
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    /* Checkerboard background for transparent images */
    .canvas-container {
        background-image: linear-gradient(45deg, #808080 25%, transparent 25%), 
                          linear-gradient(-45deg, #808080 25%, transparent 25%), 
                          linear-gradient(45deg, transparent 75%, #808080 75%), 
                          linear-gradient(-45deg, transparent 75%, #808080 75%);
        background-size: 20px 20px;
        background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
        background-color: #404040;
        border-radius: 10px;
        padding: 10px;
        display: flex;
        justify_content: center;
        align-items: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .stButton>button {
        width: 100%;
        border-radius: 20px;
    }
    h1 {
        text-align: center;
        color: #ffffff;
        font-weight: 300;
        font-size: 2.5rem;
    }
    div[data-testid="stFileUploader"] {
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("AI Canvas Studio")
st.markdown("<p style='text-align: center; color: #aaaaaa;'>拖入圖片，自定義去背、裁切、與排版流程。</p>", unsafe_allow_html=True)


# Move heavy imports here
try:
    from PIL import Image
except ImportError:
    st.error("PIL 尚未安裝")
    st.stop()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 功能控制")
    
    # 功能開關
    use_rembg = st.toggle("✨ AI 自動去背", value=True)
    use_crop = st.toggle("✂️ 自動裁切多餘邊緣", value=True)
    use_canvas = st.toggle("🎨 調整大小並置中 (畫布)", value=True)

    st.divider()

    if use_rembg:
        model_name = st.selectbox("核心模型", ["u2netp (快速)", "u2net (細緻)"], index=0)
        model_type = "u2net" if "細緻" in model_name else "u2netp"
    
    if use_canvas:
        st.subheader("畫布設定")
        col1, col2 = st.columns(2)
        with col1:
            target_w = st.number_input("寬度", value=1080, step=10)
        with col2:
            target_h = st.number_input("高度", value=1080, step=10)
            
        padding_per = st.slider("主體佔比 (%)", 50, 100, 90)
        
        is_transparent = st.toggle("透明背景", value=True)
        if not is_transparent:
            bg_color = st.color_picker("背景顏色", "#ffffff")
        else:
            bg_color = "#000000" # fallback
    else:
        st.info("💡 關閉畫布模式：將輸出原始大小的圖片。")

@st.cache_resource
def get_model(model_name):
    from rembg import new_session
    # 下載並快取模型 session
    if 'model_downloaded' not in st.session_state:
        status_placeholder = st.empty()
        with status_placeholder.status("正在初始化 AI 引擎...", expanded=True) as status:
            st.write("正在下載模型數據，請稍候...")
            session = new_session(model_name)
            st.session_state.model_downloaded = True
            status.update(label="AI 引擎準備就緒", state="complete", expanded=False)
            return session
    else:
        return new_session(model_name)

# --- 檔案上傳 ---
uploaded_files = st.file_uploader("", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, label_visibility="collapsed")

if uploaded_files:
    # 畫布區域
    st.divider()
    result_container = st.container()
    
    # 儲存處理後的結果供下載
    processed_images = []
    
    # 處理邏輯
    with result_container:
        cols = st.columns(4) # Grid layout
        
        for idx, uploaded_file in enumerate(uploaded_files):
            col_idx = idx % 4
            current_col = cols[col_idx]
            
            with current_col:
                # 顯示處理中狀態
                status_text = st.empty()
                status_text.caption(f"⏳ 處理中: {uploaded_file.name}...")
                
                try:
                    # 1. 讀取圖片 & 轉換
                    input_image = Image.open(uploaded_file).convert("RGBA")
                    current_img = input_image
                    
                    # 2. 去背 (Optional)
                    if use_rembg:
                        from rembg import remove
                        session = get_model(model_type)
                        current_img = remove(current_img, session=session)
                    
                    # 3. 偵測邊緣並裁切 (Optional)
                    if use_crop:
                        bbox = current_img.getbbox()
                        if bbox:
                            current_img = current_img.crop(bbox)
                        else:
                            # 如果是全透明，crop 可能會失敗或回傳 None (視版本而定)，這裡做個保護
                            pass 

                    # 4. 等比例縮放 & 置中 (Optional - Canvas Mode)
                    final_result = current_img
                    
                    if use_canvas:
                        # 計算縮放
                        orig_w, orig_h = current_img.size
                        if orig_w > 0 and orig_h > 0: # 避免空圖片錯誤
                            ratio = min((target_w * padding_per / 100) / orig_w, (target_h * padding_per / 100) / orig_h)
                            new_size = (int(orig_w * ratio), int(orig_h * ratio))
                            resized_img = current_img.resize(new_size, Image.Resampling.LANCZOS)
                            
                            # 建立畫布
                            fill_color = (0, 0, 0, 0) if is_transparent else bg_color
                            final_canvas = Image.new("RGBA", (target_w, target_h), fill_color)
                            
                            # 置中貼上
                            offset = ((target_w - new_size[0]) // 2, (target_h - new_size[1]) // 2)
                            final_canvas.paste(resized_img, offset, resized_img)
                            final_result = final_canvas
                            
                    # 顯示結果
                    status_text.markdown(f"""
                    <div class="canvas-container">
                             {uploaded_file.name}
                    </div>
                    """, unsafe_allow_html=True) 
                    
                    st.image(final_result, use_container_width=True)
                    status_text.empty()
                    
                    # 存入記憶體
                    buf = io.BytesIO()
                    final_result.save(buf, format="PNG")
                    processed_images.append((uploaded_file.name, buf.getvalue()))

                except Exception as e:
                    st.error(f"錯誤: {e}")

    # --- 批量下載邏輯 ---
    if processed_images:
        st.divider()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zip_file:
            for name, data in processed_images:
                # 修改副檔名為 png
                base_name = os.path.splitext(name)[0] + ".png"
                zip_file.writestr(base_name, data)
        
        st.download_button(
            label="📦 下載所有成品 (ZIP)",
            data=zip_buf.getvalue(),
            file_name="canvas_results.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )
