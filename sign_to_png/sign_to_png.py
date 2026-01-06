import os
from PIL import Image
import numpy as np

def create_feathered_signature(input_path, bg_threshold=220, ink_threshold=100, make_solid_black=True):
    """
    将图片背景转为透明，并带有柔和的羽化过渡效果。
    原理：利用两个阈值之间的线性插值来计算 Alpha 透明度。

    :param input_path: 输入路径
    :param bg_threshold: 背景阈值 (推荐 200-240)。高于此亮度的像素将完全透明。越高越难去背景。
    :param ink_threshold: 笔迹阈值 (推荐 50-150)。低于此亮度的像素将完全不透明（实心）。
                         ** bg_threshold 和 ink_threshold 之间的差值决定了羽化区域的大小。差值越大，边缘越柔和。**
    :param make_solid_black: 是否将笔迹强制染成纯黑色。建议 True，此时签名看起来更清晰专业。
                             如果选 False，将保留原图的笔迹颜色（比如蓝色圆珠笔或带噪点的灰色）。
    """
    try:
        # 1. 打开图片并转为灰度图 (L模式)，用于计算 Alpha 通道
        img = Image.open(input_path)
        gray_img = img.convert("L")
        
        # 将 PIL 图像转换为 numpy 数组，使用 float32 进行高精度计算
        gray_arr = np.array(gray_img, dtype=np.float32)

        # ===========================
        # 核心算法：计算 Alpha 通道
        # ===========================
        
        # 初始化一个全透明的 Alpha 层
        alpha_arr = np.zeros_like(gray_arr)

        # --- 情况 A: 纯背景区域 ---
        # (gray_arr >= bg_threshold) 的区域保持为 0 (全透明)，无需操作

        # --- 情况 B: 纯笔迹中心区域 ---
        # 比 ink_threshold 更黑的区域，设为全不透明 (255)
        alpha_arr[gray_arr <= ink_threshold] = 255

        # --- 情况 C: 羽化过渡区域 (魔法发生地) ---
        # 介于两个阈值之间的区域，进行线性插值计算
        # 公式含义：越接近 bg_threshold，值越小；越接近 ink_threshold，值越大
        mask_feather = (gray_arr > ink_threshold) & (gray_arr < bg_threshold)
        
        # 防止除以零错误（虽然设置上应避免 ink 等于 bg）
        if bg_threshold != ink_threshold:
             # 插值计算公式，结果映射到 0-255 之间
            alpha_arr[mask_feather] = (bg_threshold - gray_arr[mask_feather]) / (bg_threshold - ink_threshold) * 255

        # 将计算出的 Alpha 通道数据转回 uint8 格式 (图片通用格式)
        alpha_uint8 = np.clip(alpha_arr, 0, 255).astype(np.uint8)
        final_alpha_img = Image.fromarray(alpha_uint8, mode='L')

        # ===========================
        # 合成最终图像
        # ===========================
        
        if make_solid_black:
            # 创建一个纯黑色的 RGB 底图
            foreground_img = Image.new("RGB", img.size, (0, 0, 0))
        else:
            # 使用原图的 RGB 颜色
            foreground_img = img.convert("RGB")
            
        # 将 RGB 底图和计算好的 Alpha 通道合并
        foreground_img.putalpha(final_alpha_img)
        
        # 保存
        file_name, file_ext = os.path.splitext(input_path)
        output_path = f"{file_name}_feathered.png"
        foreground_img.save(output_path, "PNG")
        print(f"✅ 羽化处理完成！已保存为: {output_path}")
        print(f"   (参数: 背景阈值={bg_threshold}, 笔迹阈值={ink_threshold})")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    # --- 配置区域 ---
    input_file = r"cyj.jpg" 
    
    # 【重要】如何调整这两个参数来控制羽化：
    # 
    # 1. 背景阈值 (bg_threshold): 
    #    控制多白才算背景。如果背景去不干净，调低它 (如 200)。如果把浅色笔迹也去掉了，调高它 (如 240)。
    #
    # 2. 笔迹阈值 (ink_threshold):
    #    控制多黑才算实心笔迹。如果希望笔迹看起来更有深浅层次感，调高它 (如 150)。如果希望笔迹尽量黑实，调低它 (如 80)。
    #
    # 3. 羽化程度:
    #    这两个值的差值 (230 - 100 = 130) 越大，边缘过渡越柔和（羽化范围越大）。
    
    # 针对一般手机拍照的白纸黑字，这组参数效果通常不错：
    bg_val = 130
    ink_val = 80
    
    # 是否强制变成纯黑签字（推荐 True，更像电子签）
    force_black = True 

    create_feathered_signature(input_file, bg_val, ink_val, force_black)