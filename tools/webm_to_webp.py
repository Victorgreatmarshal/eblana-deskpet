"""
把 Spine 待机动画的录屏 WebM（背景色被烘焙进画面、没有真正的透明通道）
转成桌宠可直接播放的透明循环动画 WebP。

用法（开发时使用，运行桌宠本身不需要这些依赖）：
    pip install numpy pillow scipy        # 另需系统里有带 libvpx 的 ffmpeg
    python tools/webm_to_webp.py 输入.webm assets/official/chibi_idle.webp

处理流程：
1. ffmpeg 以固定帧率解码为 RGBA 帧；
2. 自动寻找循环点（与第 1 帧最接近的后续帧），只保留一个完整周期，首尾无缝；
3. 抠图：与画面边缘连通的近背景色区域 + 较大的封闭背景块视为背景；
   贴着背景的边缘带用邻域最深的前景色反推透明度并去色溢，避免浅色描边；
4. 裁切到所有帧的公共包围盒，编码为循环动画 WebP。
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def extract_frames(webm: Path, out_dir: Path, fps: int):
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-c:v", "libvpx-vp9", "-i", str(webm),
            "-vf", f"fps={fps}", "-pix_fmt", "rgba",
            str(out_dir / "%04d.png"),
        ],
        check=True,
    )
    return sorted(out_dir.glob("*.png"))


def find_loop_length(frames, min_frames: int) -> int:
    """返回循环帧数：与第 0 帧差异最小的后续帧序号"""
    small = [np.asarray(f.resize((125, 125), Image.BILINEAR), dtype=np.float32) for f in frames]
    diffs = [float(np.abs(s - small[0]).mean()) for s in small]
    candidates = range(min_frames, len(frames))
    if not candidates:
        return len(frames)
    return min(candidates, key=lambda i: diffs[i])


def key_frame(rgb, hard=4, pocket_min=120, band=3.0, speck_max=60, faint_max_area=3000, faint_d=16):
    c = rgb.astype(np.float32)
    border = np.concatenate(
        [c[:8].reshape(-1, 3), c[-8:].reshape(-1, 3), c[:, :8].reshape(-1, 3), c[:, -8:].reshape(-1, 3)]
    )
    bg = np.median(border, axis=0)
    d = np.abs(c - bg).max(axis=2)

    # 背景：与边缘连通的近背景色区域，以及较大的封闭背景块（例如枪杆与身体之间）
    seed = d <= hard
    labels, n = ndimage.label(seed)
    edge_ids = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    keep = sizes >= pocket_min
    keep[edge_ids] = True
    keep[0] = False
    bg_mask = keep[labels]

    # 去掉压缩噪点形成的孤立小块，以及很淡的小块
    fg_labels, m = ndimage.label(~bg_mask)
    fg_sizes = np.bincount(fg_labels.ravel(), minlength=m + 1)
    fg_maxd = np.asarray(ndimage.maximum(d, fg_labels, index=np.arange(m + 1)))
    drop = (fg_sizes <= speck_max) | ((fg_sizes <= faint_max_area) & (fg_maxd <= faint_d))
    drop[0] = False
    bg_mask |= drop[fg_labels]

    dist = ndimage.distance_transform_edt(~bg_mask)
    edge = (~bg_mask) & (dist <= band)

    # 边缘像素的前景参考色 F：邻域内离背景色最远（通常是深色描边）的前景像素
    h, w = d.shape
    flat_idx = np.arange(h * w, dtype=np.int64).reshape(h, w)
    key = np.where(bg_mask, -1, d.astype(np.int64) * (h * w) + flat_idx)
    best = ndimage.maximum_filter(key, size=int(band) * 2 + 3)
    F = c.reshape(-1, 3)[np.clip(best, 0, None) % (h * w)].reshape(h, w, 3)

    alpha = np.where(bg_mask, 0.0, 1.0).astype(np.float32)
    color = c.copy()
    v = F[edge] - bg
    u = c[edge] - bg
    denom = (v * v).sum(axis=1)
    a = np.where(denom > 25.0 ** 2, (u * v).sum(axis=1) / np.maximum(denom, 1e-6), 1.0)
    a = np.clip(a, 0.0, 1.0)
    a[a < 0.06] = 0.0
    alpha[edge] = a
    # 去色溢：C = aF + (1-a)B  =>  前景色 = B + (C - B) / a
    color[edge] = bg + u / np.maximum(a, 1e-3)[:, None]

    # 边缘带处理后与主体断开的小碎块
    final_labels, k = ndimage.label(alpha > 0)
    final_sizes = np.bincount(final_labels.ravel(), minlength=k + 1)
    tiny = final_sizes <= 150
    tiny[0] = False
    alpha[tiny[final_labels]] = 0
    color[alpha <= 0] = 0
    return np.dstack([np.clip(color, 0, 255), alpha * 255]).round().astype(np.uint8)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("webm", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--loop-frames", type=int, default=0, help="手动指定循环帧数；0 为自动检测")
    parser.add_argument("--quality", type=int, default=90)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        paths = extract_frames(args.webm, Path(tmp), args.fps)
        frames = [Image.open(p).convert("RGB") for p in paths]

    loop = args.loop_frames or find_loop_length(frames, min_frames=args.fps)
    frames = frames[:loop]
    print(f"解码 {len(paths)} 帧，循环 {loop} 帧（{loop / args.fps:.2f} 秒）")

    keyed = [Image.fromarray(key_frame(np.asarray(f)), "RGBA") for f in frames]
    alpha = np.stack([np.asarray(f)[..., 3] for f in keyed])
    ys, xs = np.where((alpha > 0).any(axis=0))
    pad = 4
    box = (
        max(0, int(xs.min()) - pad),
        max(0, int(ys.min()) - pad),
        min(keyed[0].width, int(xs.max()) + 1 + pad),
        min(keyed[0].height, int(ys.max()) + 1 + pad),
    )
    keyed = [f.crop(box) for f in keyed]

    # 每帧时长取整到毫秒，并让总时长与原始节奏一致（30fps → 33/33/34ms）
    durations, acc = [], 0.0
    for i in range(len(keyed)):
        nxt = round((i + 1) * 1000 / args.fps)
        durations.append(nxt - round(acc))
        acc = nxt
    args.output.parent.mkdir(parents=True, exist_ok=True)
    keyed[0].save(
        args.output,
        save_all=True,
        append_images=keyed[1:],
        duration=durations,
        loop=0,
        lossless=False,
        quality=args.quality,
        alpha_quality=100,
        method=6,
    )
    print(f"输出 {args.output}：{keyed[0].width}x{keyed[0].height}，{args.output.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    sys.exit(main())
