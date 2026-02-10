import streamlit as st
import io
import zipfile
import os

# 頁面設定 (must be the first streamlit command)
st.set_page_config(page_title="AI 批量去背縮放工具", layout="wide")

st.title("🖼️ AI 批量去背 & 等比例縮放工具")
st.markdown("正在載入 AI 模型，請稍候... (首次執行可能需要下載模型)")

# Move heavy imports here
try:
    from rembg import remove, new_session
    from PIL import Image
    st.success("模型載入完成！")
except Exception as e:
    st.error(f"載入模型失敗: {e}")
    st.stop()

# --- 側邊欄設定 ---
st.sidebar.header("⚙️ 參數設定")
model_name = st.sidebar.selectbox("選擇 AI 模型", ["u2net (標準 - 效果較好)", "u2netp (輕量 - 速度快)"], index=0)
model_type = "u2net" if "標準" in model_name else "u2netp"

@st.cache_resource
def get_model(model_name):
    # 下載並快取模型 session
    return new_session(model_name)

# 預先載入模型 (觸發下載)
if 'model_loaded' not in st.session_state:
    with st.spinner(f"正在載入 {model_type} 模型... (首次執行需下載)"):
        get_model(model_type)
    st.session_state.model_loaded = True


st.markdown("上傳多張圖片，自動去背、裁切邊緣、並按比例縮放置中。")


target_w = st.sidebar.number_input("目標寬度 (px)", value=1080, step=10)
target_h = st.sidebar.number_input("目標高度 (px)", value=1080, step=10)
padding_per = st.sidebar.slider("物件佔比 (%)", 50, 100, 90)
bg_color = st.sidebar.color_picker("背景顏色 (若不選透明)", "#ffffff")
is_transparent = st.sidebar.checkbox("使用透明背景", value=True)

# --- 檔案上傳 ---
uploaded_files = st.file_uploader("請選擇或拖入圖片 (支援多檔案)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"已選取 {len(uploaded_files)} 張圖片，準備處理...")
    
    # 儲存處理後的結果供下載
    processed_images = []
    
    # 建立進度條
    progress_bar = st.progress(0)
    
    for idx, uploaded_file in enumerate(uploaded_files):
        # 1. 讀取圖片
        input_image = Image.open(uploaded_file).convert("RGBA")
        
        # 2. 去背
        with st.spinner(f"正在處理第 {idx+1} 張..."):
            session = get_model(model_type)
            no_bg_img = remove(input_image, session=session)
        
        # 3. 偵測邊緣並裁切
        bbox = no_bg_img.getbbox()
        if bbox:
            cropped_img = no_bg_img.crop(bbox)
            
            # 4. 等比例縮放
            orig_w, orig_h = cropped_img.size
            ratio = min((target_w * padding_per / 100) / orig_w, (target_h * padding_per / 100) / orig_h)
            new_size = (int(orig_w * ratio), int(orig_h * ratio))
            resized_img = cropped_img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 5. 建立畫布
            fill_color = (0, 0, 0, 0) if is_transparent else bg_color
            final_canvas = Image.new("RGBA", (target_w, target_h), fill_color)
            
            # 置中貼上
            offset = ((target_w - new_size[0]) // 2, (target_h - new_size[1]) // 2)
            final_canvas.paste(resized_img, offset, resized_img)
            
            # 存入記憶體
            buf = io.BytesIO()
            final_canvas.save(buf, format="PNG")
            processed_images.append((uploaded_file.name, buf.getvalue()))
            
        # 更新進度條
        progress_bar.progress((idx + 1) / len(uploaded_files))

    st.success("✨ 全部處理完成！")

    # --- 批量下載邏輯 ---
    if processed_images:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zip_file:
            for name, data in processed_images:
                # 修改副檔名為 png
                base_name = os.path.splitext(name)[0] + ".png"
                zip_file.writestr(base_name, data)
        
        st.download_button(
            label="📂 一鍵下載所有處理後的圖片 (ZIP)",
            data=zip_buf.getvalue(),
            file_name="processed_images.zip",
            mime="application/zip"
        )

        # 預覽最後一張
        st.image(final_canvas, caption="最後一張處理預覽", width=400)
