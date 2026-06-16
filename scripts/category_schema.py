# Spec schema per category — measurable specs only.
# Order matters: this is the display order on each card.
# Optional measurables can appear if present but won't be flagged missing.

SCHEMA = {
    "wheelchair": {
        "core": ["座高", "座闊", "總外闊", "重量", "承重"],
        "optional": ["座深", "背高", "扶手高"],
    },
    "shower": {
        "core": ["座高", "座闊", "總尺寸", "承重"],
        "optional": ["重量", "總外闊"],
    },
    "commode": {
        "core": ["座高", "座闊", "總外闊", "承重"],
        "optional": ["尺寸", "總尺寸", "座深", "背高", "適合座廁高", "適合座廁闊", "重量", "腳踏高", "腳踏伸縮距離"],
    },
    "bathboard": {
        "core": ["尺寸", "承重"],
        "optional": ["適合浴缸闊度", "總闊", "深度"],
    },
    "toiletriser": {
        "core": ["尺寸", "高度", "承重"],
        "optional": ["孔徑", "適合坐廁總外闊", "深度", "闊度"],
    },
    "handrail": {
        "core": ["長度", "承重"],
        "optional": ["直徑", "離牆高度"],
    },
    "bedrail": {
        "core": ["尺寸", "承重"],
        "optional": ["床欄高度"],
    },
    "bed": {
        "core": ["尺寸", "承重"],
        "optional": ["離地高度", "升降範圍", "床面尺寸"],
    },
    "mattress": {
        "core": ["充氣後尺寸", "承重"],
        "optional": ["管條數量", "氣泵流量"],
    },
    "ramp": {
        "core": ["長度", "闊度", "高度", "承重"],
        "optional": [],
    },
    "reacher": {
        "core": ["長度"],
        "optional": ["重量", "夾頭闊度"],
    },
    "sockaid": {
        "core": ["長度"],
        "optional": ["重量"],
    },
}

# Label translations: zh -> en
LABEL_ZH_TO_EN = {
    "座高": "Seat height",
    "腳踏高": "Footrest height",
    "腳踏伸縮距離": "Footrest extension",
    "床面尺寸": "Mattress size",
    "總闊": "Overall width",
    "座闊": "Seat width",
    "座深": "Seat depth",
    "背高": "Back height",
    "扶手高": "Armrest height",
    "總外闊": "Overall width",
    "總尺寸": "Overall size",
    "尺寸": "Dimensions",
    "孔徑": "Aperture",
    "深度": "Depth",
    "厚度": "Thickness",
    "重量": "Weight",
    "承重": "Max load",
    "高度": "Height",
    "長度": "Length",
    "闊度": "Width",
    "直徑": "Diameter",
    "離牆高度": "Wall clearance",
    "離地高度": "Ground clearance",
    "升降範圍": "Height range",
    "床欄高度": "Rail height",
    "適合座廁高": "Fits toilet height",
    "適合座廁闊": "Fits toilet width",
    "適合坐廁總外闊": "Fits toilet outer width",
    "適合浴缸闊度": "Fits bathtub width",
    "充氣後尺寸": "Inflated size",
    "管條數量": "Number of tubes",
    "氣泵流量": "Pump flow",
    "夾頭闊度": "Jaw width",
}

# Reverse + common aliases
LABEL_EN_TO_ZH = {v: k for k, v in LABEL_ZH_TO_EN.items()}
LABEL_EN_TO_ZH.update({
    "Footrest height": "腳踏高",
    "Mattress dimensions": "床面尺寸",
    "Weight capacity": "承重",
    "Load capacity": "承重",
    "Max load": "承重",
    "Overall": "總尺寸",
    "Overall dimensions": "總尺寸",
    "Overall size": "總尺寸",
    "Size": "尺寸",
    "Heights": "高度",  # plural variant
    "Lengths": "長度",
    "Widths": "闊度",
    "Height": "高度",
    "Length": "長度",
    "Width": "闊度",
    "Weight": "重量",
    "Diameter": "直徑",
    "Depth": "深度",
    "Wall clearance": "離牆高度",
    "Fits bath width": "適合浴缸闊度",
    "Air tubes": "管條數量",
    "Air pump flow": "氣泵流量",
    "Pump airflow": "氣泵流量",
    "Number of tubes": "管條數量",
    "Inflated size": "充氣後尺寸",
    "Height range": "升降範圍",
})

# Chinese label aliases: variant zh label -> canonical zh label
# Used during normalize when the source data uses an alternate phrasing.
LABEL_ZH_ALIAS = {
    "外型尺寸": "總尺寸",
    "外型尺寸 (打開後)": "總尺寸",
    "總外闊": "總外闊",  # canonical (no-op safety)
    "離地": "離地高度",
    "氣泵空氣流量": "氣泵流量",
    "氣泵充氣流量": "氣泵流量",
    "床管": "管條數量",
    "厚度 / 高度": "高度",
    "厚度/高度": "高度",
}
