#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端渲染全球彩色地势底图（Natural Earth Cross-blended Hypsometric Tints）。
1:10m 高分辨率源（21600x10800，含海底分层）→ 降采样到 5400 宽 → JPEG。
输出：terrain/basemap.jpg
"""
import urllib.request, zipfile, io, os
import numpy as np
from PIL import Image
import tifffile

URL = 'https://naciscdn.org/naturalearth/10m/raster/HYP_HR_SR_OB_DR.zip'
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'basemap.jpg')
TARGET_W = 5400  # 输出宽度（像素），为旧版 2700 的两倍

req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 conflict-monitor-bot'})
print('downloading HYP_HR_SR_OB_DR.zip (1:10m, large) ...', flush=True)
data = urllib.request.urlopen(req, timeout=900).read()
print('downloaded', len(data), 'bytes', flush=True)

z = zipfile.ZipFile(io.BytesIO(data))
tif_name = [n for n in z.namelist() if n.lower().endswith('.tif')][0]
print('tif:', tif_name, flush=True)
arr = tifffile.imread(io.BytesIO(z.read(tif_name)))
print('array shape:', arr.shape, arr.dtype, flush=True)

# 规整为 RGB uint8
if arr.ndim == 2:
    arr = np.stack([arr] * 3, axis=-1)
elif arr.ndim == 3 and arr.shape[2] >= 4:
    arr = arr[:, :, :3]
arr = np.ascontiguousarray(arr.astype('uint8'))

img = Image.fromarray(arr)
H, W = arr.shape[:2]
if W > TARGET_W:
    th = max(1, int(H * TARGET_W / W))
    img = img.resize((TARGET_W, th), Image.LANCZOS)
img.save(OUT, 'JPEG', quality=88, optimize=True, progressive=True)
print('OK', OUT, os.path.getsize(OUT), 'bytes, size', img.size, flush=True)
