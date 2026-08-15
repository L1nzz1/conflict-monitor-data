#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端渲染全球彩色地势底图（Natural Earth Cross-blended Hypsometric Tint）。
下载 HYP_50M_SR_W（等距圆柱投影的全球彩色地势 + 山体阴影 + 海洋）→ 转 PNG。
输出：terrain/basemap.png
"""
import urllib.request, zipfile, io, os
import numpy as np
from PIL import Image
import tifffile

URL = 'https://naciscdn.org/naturalearth/50m/raster/HYP_50M_SR_W.zip'
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'basemap.png')
TARGET_W = 2700  # 输出宽度（像素）

req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
print('downloading HYP_50M_SR_W.zip ...', flush=True)
data = urllib.request.urlopen(req, timeout=300).read()
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
img.save(OUT, 'PNG', optimize=True)
print('OK', OUT, os.path.getsize(OUT), 'bytes, size', img.size, flush=True)
