#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端渲染重大战争地区 SRTM 山体阴影地形图（GitHub Actions 用）。
下载 SRTM3 90m 瓦片 → numpy 拼接 → hillshade → 输出 PNG 到 terrain/ 目录。
用法: python render_terrain.py [ukr|sud|mmr|all]
"""
import os, sys, gzip, urllib.request, math, concurrent.futures
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

SRTM_BASE = 'https://s3.amazonaws.com/elevation-tiles-prod/skadi'
BASE = os.path.dirname(os.path.abspath(__file__))  # repo/terrain
OUT_DIR = BASE

# 中文字体（Actions 里 fonts-noto-cjk 提供）
zh = None
for f in fm.fontManager.ttflist:
    if any(k in f.name for k in ('CJK', 'Noto Sans SC', 'WenQuanYi', 'YaHei', 'SimHei')):
        zh = fm.FontProperties(fname=f.fname)
        break

# 地区定义：名称 + 包围盒(纬度min,max / 经度min,max) + 关键地点(名称,纬度,经度)
REGIONS = {
    'ukr': {
        'name': '乌克兰东部 · 顿巴斯',
        'lat': (47.0, 51.0), 'lon': (33.0, 41.0),
        'points': [('哈尔科夫', 50.0, 36.2), ('顿涅茨克', 48.0, 37.8),
                   ('卢甘斯克', 48.6, 39.3), ('马里乌波尔', 47.1, 37.5)],
    },
    'sud': {
        'name': '苏丹 · 达尔富尔—科尔多凡',
        'lat': (11.0, 16.0), 'lon': (22.0, 32.0),
        'points': [('法希尔', 13.6, 25.3), ('尼亚拉', 12.05, 24.88),
                   ('喀土穆', 15.6, 32.5), ('欧拜伊德', 13.18, 30.22)],
    },
    'mmr': {
        'name': '缅甸 · 中北部山地',
        'lat': (16.5, 24.0), 'lon': (94.0, 101.0),
        'points': [('内比都', 19.8, 96.1), ('曼德勒', 21.98, 96.08),
                   ('腊戍', 22.94, 97.75), ('密支那', 25.38, 97.39)],
    },
}


def fetch_tile(tl_lat, tl_lon):
    """下载一片 1°x1° .hgt.gz，自动识别分辨率并降采样到 ~90m（1201 边）。"""
    ns = 'N' if tl_lat >= 0 else 'S'
    ew = 'E' if tl_lon >= 0 else 'W'
    name = f'{ns}{abs(tl_lat):02d}{ew}{abs(tl_lon):03d}'
    url = f'{SRTM_BASE}/{ns}{abs(tl_lat):02d}/{name}.hgt.gz'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = gzip.decompress(r.read())
    n = int(round(np.sqrt(len(raw) / 2)))
    a = np.frombuffer(raw, dtype='>i2').reshape(n, n).astype(np.float32)
    a[a <= -1000] = 0.0  # void
    if n != 1201:  # 统一线性重采样到 1201，兼容 1801/3601 等不同分辨率
        idx = np.linspace(0, n - 1, 1201).astype(int)
        a = a[idx][:, idx]
    return tl_lat, tl_lon, a


def build_dem(lat_rng, lon_rng):
    """并发下载 + 拼接包围盒内所有瓦片，返回 (elev, lat_axis, lon_axis)。"""
    lat0, lat1 = lat_rng
    lon0, lon1 = lon_rng
    tlat0, tlon0 = int(math.floor(lat0)), int(math.floor(lon0))
    tlat1, tlon1 = int(math.ceil(lat1)), int(math.ceil(lon1))
    rows, cols = tlat1 - tlat0, tlon1 - tlon0
    N = 1201
    tiles = [(tlat0 + ri, tlon0 + ci) for ri in range(rows) for ci in range(cols)]
    big = np.zeros((rows * N, cols * N), dtype=np.float32)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for tl_lat, tl_lon, a in ex.map(lambda p: fetch_tile(*p), tiles):
            ri = tl_lat - tlat0
            ci = tl_lon - tlon0
            big_row = (rows - 1 - ri) * N  # 最北瓦片置顶，保证纬度单调（北→南）
            big[big_row:big_row + N, ci * N:(ci + 1) * N] = a
    lat_axis = np.linspace(tlat1, tlat0, rows * N)
    lon_axis = np.linspace(tlon0, tlon1, cols * N)
    return big, lat_axis, lon_axis


def hillshade(elev, azimuth=315.0, altitude=45.0):
    x, y = np.gradient(elev)
    slope = np.pi / 2 - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    az = np.deg2rad(azimuth)
    alt = np.deg2rad(altitude)
    s = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos((az - np.pi / 2) - aspect)
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


def render(key):
    r = REGIONS[key]
    print(f'[{key}] 下载拼接中...', flush=True)
    elev, lat_axis, lon_axis = build_dem(r['lat'], r['lon'])
    hs = hillshade(elev)
    water = elev <= 0.0
    rgb = np.zeros((elev.shape[0], elev.shape[1], 3), dtype=np.float32)
    gray = 0.45 + 0.55 * hs
    rgb[:, :, 0] = gray; rgb[:, :, 1] = gray; rgb[:, :, 2] = gray
    rgb[water] = (0.08, 0.13, 0.22)

    dpi = 100
    fig = plt.figure(figsize=(8, 6), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(rgb, extent=[lon_axis[0], lon_axis[-1], lat_axis[-1], lat_axis[0]],
              aspect='auto', interpolation='bilinear')
    for name, plat, plon in r['points']:
        if r['lat'][0] <= plat <= r['lat'][1] and r['lon'][0] <= plon <= r['lon'][1]:
            ax.plot(plon, plat, 'o', ms=7, mfc='#ff3b30', mec='white', mew=1.5, zorder=5)
            ax.text(plon, plat + 0.28, name, fontsize=11, color='white',
                    ha='center', va='bottom', fontproperties=zh,
                    bbox=dict(boxstyle='round,pad=0.25', fc='black', ec='none', alpha=0.55))
    ax.text(0.5, 0.985, r['name'], transform=ax.transAxes, fontsize=15,
            color='white', ha='center', va='top', fontproperties=zh,
            bbox=dict(boxstyle='round,pad=0.4', fc='black', ec='none', alpha=0.5))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlim(lon_axis[0], lon_axis[-1]); ax.set_ylim(lat_axis[-1], lat_axis[0])
    out = os.path.join(OUT_DIR, key + '.png')
    fig.savefig(out, dpi=dpi, facecolor='#0a0e1a', bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    print(f'OK {key} -> {out} {os.path.getsize(out)} bytes', flush=True)


if __name__ == '__main__':
    keys = sys.argv[1:] or ['ukr']
    if keys == ['all']:
        keys = list(REGIONS)
    for k in keys:
        render(k)
