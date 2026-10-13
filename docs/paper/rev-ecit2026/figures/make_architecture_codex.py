"""Stdlib-only architecture artwork. Run, then render using rsvg-convert.
180 mm wide; 62.18 mm tall. Minimum 15.5 SVG units = 7.19 pt.
"""
from pathlib import Path
from html import escape
W, H = 1100, 380
INK, BLUE, TEAL, GREY = '#24313d', '#315e81', '#28776f', '#697580'
a = [f'<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="{180*H/W:.6f}mm" viewBox="0 0 {W} {H}">', '<defs>']
for name, color in [('blue', BLUE), ('teal', TEAL), ('grey', GREY)]:
    a.append(f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="{color}"/></marker>')
a += ['</defs>', '<rect width="1100" height="380" fill="white"/>']
def text(x,y,s,size=16,bold=False,color=INK,anchor='middle',mono=False):
    font = 'Menlo,monospace' if mono else 'Arial,Helvetica,sans-serif'
    a.append(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{"700" if bold else "400"}" text-anchor="{anchor}" fill="{color}">{escape(s)}</text>')
def rect(x,y,w,h,fill='#f4f6f8',stroke='#cad2d9',r=7):
    a.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
def path(d,color=BLUE,head='blue',dash=False):
    a.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.7"'+(' stroke-dasharray="4 3"' if dash else '')+(f' marker-end="url(#{head})"' if head else '')+'/>')
def robot(x,y):
    rect(x,y,22,16,'#fff',BLUE,3)
    path(f'M{x+11} {y}v-4',BLUE,None)
    for dx in (7,15): a.append(f'<circle cx="{x+dx}" cy="{y+7}" r="1.6" fill="{BLUE}"/>')
# Header and compact input.
text(12,23,'AlignmentGraph-ISD',22,True,anchor='start')
text(1088,23,'Thiết kế dạy học đa tác tử',16,color=GREY,anchor='end')
rect(12,39,266,32,'#fff')
text(145,60,'Bản mô tả thiết kế',16)
path('M145 71V91')
text(145,88,'',16)
text(145,111,'Designer · Backward Design',17,True)
text(145,132,'Lượt cố định 1 → 6 · chỉ 1 tác tử',15.5,color=GREY)
labels=['Phân tích nhu cầu','Mục tiêu & mô-đun','Đánh giá','Hoạt động','Học liệu','Triển khai']
for i,label in enumerate(labels):
    y=143+i*27
    active=i==2
    rect(12,y,266,25,'#e9f1f7' if active else '#f5f6f7',BLUE if active else '#d8dfe4',4)
    text(29,y+18,str(i+1),16,True,color=BLUE if active else GREY)
    if active: robot(47,y+5)
    text(78 if active else 47,y+18,label,16,active,anchor='start')
# Dispatch bracket, deliberately separate from the tool loop.
path('M12 208H5V303H34',GREY,'grey')
rect(34,303,244,39,'#fff')
robot(45,315)
text(170,319,'Developer · bước 3–6',15.5,True)
text(170,336,'1 tác tử / bộ việc',15.5,color=GREY)
# Harness is the sole route into shared state.
rect(394,78,221,230,'#edf4f4','#8bb5af')
text(504.5,103,'HARNESS',19,True,color=TEAL)
text(504.5,125,'Khung điều phối',17,True)
text(504.5,65,'Mọi tác tử qua công cụ',15.5,color=GREY)
text(504.5,160,'Đọc trạng thái',16)
path('M410 176H599',TEAL,None)
text(504.5,199,'Xác thực nộp',16)
text(504.5,224,'Ghi nút · dựng cạnh',16)
text(504.5,246,'từ ID khai báo',15.5,color=GREY)
text(504.5,283,'Kiểm tra tất định',16,True,color=TEAL)
# Act/observe loop from the currently active agent.
path('M278 210H301V152H394')
text(343,145,'Gọi công cụ',15.5,color=BLUE)
path('M394 270H302V220H278')
text(344,291,'Quan sát',15.5,color=BLUE)
text(344,313,'state /',15.5,color=GREY)
text(344,332,'COMMITTED / lỗi',15.5,color=GREY)
# Shared alignment graph: typed triad.
rect(652,78,271,230,'#fff','#8aa5bb')
text(787.5,103,'ĐỒ THỊ CĂN CHỈNH',18,True,color=BLUE)
text(787.5,125,'Trạng thái dùng chung',15.5,color=GREY)
path('M615 213H652',TEAL,'teal')
rect(739,142,97,33,'#e9f1f7','#8aa5bb')
text(787.5,164,'Mục tiêu',16,True)
path('M754 175L705 234')
path('M821 175L870 234')
text(715,204,'C3',16,True,color=BLUE)
text(861,204,'C2',16,True,color=BLUE)
rect(664,235,101,46,'#e9f1f7','#8aa5bb')
text(714.5,263,'Hoạt động',16,True)
rect(817,235,94,46,'#e9f1f7','#8aa5bb')
text(864,253,'Nhiệm vụ',15.5,True)
text(864,272,'đánh giá',15.5,True)
path('M765 258H817')
text(791,248,'C4',16,True,color=BLUE)
text(787.5,299,'+ quan hệ phụ',15.5,color=GREY)
# Graph-derived exports.
path('M923 191H943V155H956')
path('M943 191V262H956')
rect(956,129,132,63,'#f4f6f8')
text(1022,151,'Đầu ra ADDIE',16,True)
text(1022,177,'5 pha',16)
rect(956,234,132,59,'#f4f6f8')
text(1022,258,'graph.json',15.5,mono=True)
text(1022,281,'+ sổ vi phạm',15.5)
# Every violation is logged; content repairs return to the owner.
path('M504 308V352H287V201H278',TEAL,'teal')
text(339,374,'Lượt sửa → tác tử sở hữu',15.5,color=TEAL)
path('M615 294H632V324H1022V293',GREY,'grey',True)
text(809,344,'Ghi mọi vi phạm',15.5,color=GREY)
a.append('</svg>')
Path(__file__).with_name('architecture_codex.svg').write_text('\n'.join(a),encoding='utf-8')
