"""Rebuild static design artifacts only; not imported by the Flask application."""
from pathlib import Path
from html import escape
import json
import math

ROOT = Path(__file__).resolve().parent
INK = '#172F40'
MUTED = '#526575'
LINE = '#D6DFE6'
CONTROL = '#718391'
TEAL = '#096C68'
BLUE = '#164FBA'
COLORS = {0: '#F0F3F6', 1: '#087F76', 2: '#8B6700', 3: '#B84B16', 4: '#AE2442'}
LETTERS = {0: '0', 1: 'L', 2: 'M', 3: 'H', 4: 'C'}


class Sheet:
    def __init__(self, width, height, title):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
            f'<title>{escape(title)}</title>',
            '<defs><pattern id="missing" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#F0F3F6"/><path d="M-2 2L2 -2M0 8L8 0M6 10L10 6" stroke="#718391" stroke-width="1"/></pattern></defs>',
            '<style>text{font-family:Segoe UI,Arial,sans-serif;font-variant-numeric:tabular-nums} .mono{font-family:Consolas,monospace}</style>']
        self.rect(0, 0, width, height, '#FFFFFF')

    def rect(self, x, y, w, h, fill='white', stroke=None, radius=0, sw=1):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{sw}"/>')

    def text(self, x, y, value, size=14, color=INK, weight=400, anchor='start', mono=False):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" class="{"mono" if mono else ""}">{escape(str(value))}</text>')

    def line(self, x1, y1, x2, y2, color=LINE, sw=1):
        self.parts.append(f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}" stroke-width="{sw}"/>')

    def button(self, x, y, w, label, active=False, height=36, selected=False):
        self.rect(x, y, w, height, TEAL if active else '#EDF3FF' if selected else '#FFFFFF', BLUE if selected else TEAL if active else CONTROL, 4)
        self.text(x+w/2, y+height/2+5, label, 14, '#FFFFFF' if active else BLUE if selected else INK, 600 if active or selected else 400, 'middle')

    def field(self, x, y, w, label, value):
        self.rect(x, y, w, 48, '#FFFFFF', CONTROL, 4)
        self.text(x+12, y+17, label, 13, MUTED)
        self.text(x+12, y+37, value, 14, INK, 600)
        self.text(x+w-18, y+33, '⌄', 16, MUTED, anchor='middle')

    def chip(self, x, y, w, label, selected=False):
        self.rect(x, y, w, 28, '#EDF3FF' if selected else '#F5F7F9', BLUE if selected else CONTROL, 4)
        self.text(x+10, y+19, label, 13, BLUE if selected else MUTED)

    def save(self, name):
        (ROOT / f'{name}.svg').write_text('\n'.join(self.parts + ['</svg>']), encoding='utf-8')


LANES = [
    ('Error burst', {8: 4}),
    ('Timeout frequency', {6: 3}),
    ('Isolation Forest', {3: 2, 7: 3}),
    ('Event novelty', {1: 1, 5: 2}),
]
OVERALL = {i: max(d.get(i, 0) for _, d in LANES) for i in range(12)}


def cells(s, x, y, width, values, selected=None):
    cw = width / 12
    for i in range(12):
        p = values.get(i, 0)
        s.rect(round(x+i*cw+2, 2), y, round(cw-4, 2), 32, COLORS[p], CONTROL if p == 0 else None, 2)
        s.text(x+(i+.5)*cw, y+21, f'{LETTERS[p]}  1' if p else '0', 13, '#FFFFFF' if p else MUTED, 600 if p else 400, 'middle')
        if i == selected:
            s.rect(round(x+i*cw, 2), y-3, round(cw, 2), 38, 'none', '#FFFFFF', 3, 5)
            s.rect(round(x+i*cw, 2), y-3, round(cw, 2), 38, 'none', BLUE, 3, 2)


def workspace(width=1440, selected=False):
    compact = width == 1024
    margin = 20 if compact else 24
    right = width-margin
    s = Sheet(width, 1090, f'Timeline V2 — {"compact" if compact else "desktop"} design wireframe')
    s.text(margin, 22, 'DESIGN WIREFRAME · PROPOSED, NOT IMPLEMENTED', 13, MUTED, 600)
    s.text(margin, 60, 'Investigation', 24, INK, 650)
    s.text(right, 56, f'{width}px · single workspace', 13, MUTED, anchor='end')
    s.rect(margin, 80, width-margin*2, 36, '#F5F7F9')
    s.rect(margin, 80, 3, 36, TEAL)
    s.text(margin+14, 103, 'DEMO', 13, TEAL, 700)
    s.text(margin+70, 103, 'Synthetic events, scores and evidence. No model executed.', 14, MUTED)
    if compact:
        s.field(20, 132, 240, 'Source', 'Synthetic fixture')
        s.field(272, 132, 432, 'Time range', '03 Nov 2026 · 13:50–14:50')
        s.field(716, 132, 288, 'Timezone', 'Asia/Ho_Chi_Minh · +07')
        s.button(20, 194, 354, 'Search messages, hosts, detectors…')
        s.button(386, 194, 144, 'Entities: all ⌄')
        s.button(542, 194, 138, 'Priority: all ⌄')
        s.button(692, 194, 214, 'Detectors: all ⌄')
        s.button(918, 194, 86, 'Apply', True)
    else:
        s.field(24, 132, 250, 'Source', 'Synthetic fixture')
        s.field(286, 132, 422, 'Time range', '03 Nov 2026 · 13:50–14:50')
        s.field(720, 132, 270, 'Timezone', 'Asia/Ho_Chi_Minh · +07')
        s.text(right, 160, 'No connected dataset or live ingestion', 13, MUTED, anchor='end')
        s.button(24, 194, 500, 'Search messages, hosts, detectors…')
        s.button(536, 194, 170, 'Entities: all ⌄')
        s.button(718, 194, 160, 'Priority: all ⌄')
        s.button(890, 194, 330, 'Detectors: all ⌄')
        s.button(1232, 194, 88, 'Apply', True)
        s.text(1340, 217, 'Clear filters', 13, TEAL, 600)
    s.text(margin, 260, 'Applied scope: dated synthetic fixture · all hosts, services, priorities and detectors', 13, MUTED)
    if compact:
        s.text(right, 260, 'Clear filters', 13, TEAL, 600, 'end')
    panel_y, panel_h = 282, 480
    s.rect(margin, panel_y, width-margin*2, panel_h, '#FFFFFF', LINE, 4)
    s.text(margin+20, 313, 'Anomaly activity', 18, INK, 650)
    s.text(margin+20, 337, '6 anomalies in scope · 3 High / Critical', 14, MUTED)
    s.button(right-238, 299, 112, 'Severity', selected=True)
    s.button(right-126, 299, 106, 'Volume')
    s.button(margin+20, 355, 40, '‹')
    s.button(margin+68, 355, 40, '›')
    s.button(margin+120, 355, 152, 'Select range…')
    s.button(margin+284, 355, 100, 'Zoom in')
    s.button(margin+396, 355, 100, 'Zoom out')
    s.button(margin+508, 355, 112, 'Reset zoom')
    s.text(right-20, 378, 'Auto · 5 min · 12 bins', 13, MUTED, anchor='end')
    label_x = margin+20
    plot_x = margin+(196 if compact else 216)
    plot_w = right-20-plot_x
    s.line(margin+20, 403, right-20, 403)
    for idx, label in [(0, '13:50'), (2, '14:00'), (4, '14:10'), (6, '14:20'), (8, '14:30'), (10, '14:40'), (12, '14:50')]:
        anchor = 'end' if idx == 12 else 'start' if idx == 0 else 'middle'
        s.text(plot_x+idx*plot_w/12, 429, label, 13, MUTED, anchor=anchor, mono=True)
    s.text(label_x, 462, 'Overall', 14, INK, 700)
    cells(s, plot_x, 441, plot_w, OVERALL)
    s.line(margin+20, 486, right-20, 486)
    s.text(label_x, 509, '⌄ Rules · 2 detectors', 13, MUTED, 600)
    s.text(right-20, 509, 'Sort: priority ⌄', 13, TEAL, 600, 'end')
    for j, y in enumerate([520, 562]):
        label, values = LANES[j]
        s.text(label_x, y+21, label, 14, INK, 600)
        cells(s, plot_x, y, plot_w, values, 8 if selected and j == 0 else None)
    s.text(label_x, 626, '⌄ Statistical / pattern · 2 detectors', 13, MUTED, 600)
    for j, y in enumerate([638, 680], 2):
        label, values = LANES[j]
        s.text(label_x, y+21, label, 14, INK, 600)
        cells(s, plot_x, y, plot_w, values)
    legend_y = 739
    legend = [('L Low', COLORS[1]), ('M Medium', COLORS[2]), ('H High', COLORS[3]), ('C Critical', COLORS[4])]
    x = label_x
    for label, color in legend:
        s.rect(x, legend_y-12, 12, 12, color, radius=2)
        s.text(x+18, legend_y, label, 13, MUTED)
        x += 104 if compact else 116
    s.text(right-20, legend_y, 'Color = highest priority · number = count', 13, MUTED, anchor='end')
    # Fixture zero is scoped to an explicit synthetic record set, not real monitoring.
    s.text(margin, 783, '0 = no anomaly in this fixture bin · not evidence of live data coverage', 13, MUTED)
    table_top = 804
    s.rect(margin, table_top, width-margin*2, 232, '#FFFFFF', LINE, 4)
    s.text(margin+20, 835, 'Results', 18, INK, 650)
    s.text(margin+100, 834, '1 in selection / 6 in scope' if selected else '6 in scope · newest first', 14, MUTED)
    s.button(right-180, 814, 160, 'Export scoped CSV')
    if selected:
        s.rect(margin+1, 851, width-margin*2-2, 40, '#EDF3FF')
        s.rect(margin+1, 851, 3, 40, BLUE)
        s.text(margin+16, 877, 'Selected: Error burst · 14:30–14:35 +07', 14, BLUE, 600)
        s.text(right-188, 877, 'Clear selection', 13, BLUE, 600, 'end')
        s.text(right-20, 877, 'Zoom to selection', 13, BLUE, 600, 'end')
        heading_y, row_y = 914, 944
    else:
        heading_y, row_y = 875, 908
    if compact:
        col = [margin+16, margin+150, margin+282, margin+715]
        labels = ['Time / event', 'Priority', 'Signal', 'Host / service']
    else:
        col = [margin+16, margin+164, margin+312, margin+810, margin+1046]
        labels = ['Time / event', 'Priority', 'Signal', 'Host / service', 'Detector']
    for x, label in zip(col, labels):
        s.text(x, heading_y, label, 13, MUTED, 600)
    s.line(margin, heading_y+12, right, heading_y+12)
    rows = [
        ('14:32:08', 'LS-1042', '◆ Critical', 4, 'Kernel errors exceeded the baseline.', 'compute-07', 'kernel', 'Error burst'),
        ('14:28:41', 'LS-1041', '▲ High', 3, 'Unusual storage event-rate pattern.', 'storage-02', 'storage', 'Isolation Forest'),
    ]
    for j, row in enumerate(rows[:1] if selected else rows):
        yy = row_y+j*56
        if selected:
            s.rect(margin+1, yy-17, width-margin*2-2, 52, '#EDF3FF')
            s.rect(margin+1, yy-17, 3, 52, BLUE)
        time, eid, priority, sev, signal, host, service, detector = row
        s.text(col[0], yy, time, 14, INK, 600, mono=True)
        s.text(col[0], yy+19, eid, 13, MUTED)
        s.text(col[1], yy, priority, 14, COLORS[sev], 650)
        s.text(col[2], yy, signal, 14, INK)
        s.text(col[3], yy, host, 14, INK)
        s.text(col[3], yy+19, service, 13, MUTED)
        if not compact:
            s.text(col[4], yy, detector, 14, MUTED)
        s.text(right-20, yy, 'Inspect →', 13, BLUE, 600, 'end')
        s.line(margin, yy+35, right, yy+35)
    s.text(margin+20, 1020, '1–1 of 1' if selected else '1–6 of 6 · preview shows first 2 rows', 13, MUTED)
    s.text(right-20, 1020, 'Previous   /   Next', 13, MUTED, anchor='end')
    s.text(margin, 1068, 'Design proposal · synthetic scores are rankings, not probabilities or root-cause evidence.', 13, MUTED)
    return s


def evidence():
    s = workspace(1440, selected=True)
    x, w = 996, 420
    # Modal surface overlays, without squeezing the underlying timeline/table.
    s.rect(x-5, 28, 5, 1020, '#D6DFE6')
    s.rect(x, 28, w, 1020, '#FFFFFF', CONTROL, 4)
    s.text(x+24, 58, 'EVIDENCE · DEMO', 13, TEAL, 700)
    s.button(x+w-70, 40, 46, '×', height=40)
    s.text(x+24, 105, 'LS-1042', 24, INK, 700)
    s.text(x+24, 135, '◆ Critical', 16, COLORS[4], 700)
    s.text(x+24, 170, 'Kernel error volume exceeded', 16, INK, 600)
    s.text(x+24, 194, 'the configured baseline.', 16, INK, 600)
    s.text(x+24, 228, '03 Nov 2026 · 14:32:08 +07:00', 14, MUTED)
    fields = [
        ('Entity', 'compute-07 / kernel'),
        ('Detector', 'Error burst'),
        ('Detection unit', 'Time window · synthetic'),
        ('Illustrative score', '96 / 100 · not probability'),
        ('Model / rule version', 'Unavailable — fixture only'),
        ('Evidence source', 'Synthetic presentation record'),
    ]
    for i, (label, value) in enumerate(fields):
        y = 261+i*51
        s.text(x+24, y, label, 13, MUTED)
        s.text(x+24, y+21, value, 14, INK, 600)
        s.line(x+24, y+32, x+w-24, y+32)
    s.text(x+24, 601, 'Observed versus reference', 16, INK, 650)
    s.rect(x+24, 621, w-48, 81, '#F5F7F9', LINE, 4)
    s.text(x+40, 646, 'Observed (synthetic)', 13, MUTED)
    s.text(x+40, 679, '42 errors / min', 17, INK, 650)
    s.text(x+222, 646, 'Reference (synthetic)', 13, MUTED)
    s.text(x+222, 679, '3 errors / min', 17, INK, 650)
    s.text(x+24, 742, 'Synthetic evidence excerpt', 16, INK, 650)
    s.rect(x+24, 762, w-48, 119, '#F5F7F9', LINE, 4)
    for i, line in enumerate(['2026-11-03T14:32:08+07:00', '[DEMO] compute-07 kernel:', 'Kernel error volume exceeded', 'the configured baseline.']):
        s.text(x+38, 786+i*23, line, 13, INK, mono=True)
    s.text(x+24, 920, 'No real dataset or model run backs this record.', 13, MUTED)
    s.text(x+24, 943, 'The score does not establish a root cause.', 13, MUTED)
    s.line(x+24, 975, x+w-24, 975)
    s.text(x+24, 1004, 'Escape / Close returns to the selected result.', 13, MUTED)
    s.text(x+24, 1027, 'Time range, filters and timeline selection persist.', 13, MUTED)
    s.save('timeline-v2-evidence')


def states():
    s = Sheet(1440, 1040, 'Timeline V2 — proposed volume, coverage and request states')
    s.text(24, 28, 'DESIGN STATE SHEET · CONSTRUCTED EXAMPLES, NOT LIVE SOURCE STATUS', 13, MUTED, 650)
    s.text(24, 69, 'Meaning before decoration', 24, INK, 650)
    s.text(24, 98, 'Severity, count, coverage and selection have separate visual rules.', 16, MUTED)
    s.rect(24, 126, 1392, 191, '#FFFFFF', LINE, 4)
    s.text(44, 157, 'Same example bins · two exclusive modes', 16, INK, 650)
    counts = [0, 1, 3, 7, 12, 48, 96, 4]
    priorities = [0, 1, 2, 2, 3, 3, 4, 1]
    s.text(44, 201, 'Severity View', 14, INK, 600)
    s.text(44, 259, 'Volume View', 14, INK, 600)
    ramp = ['#DCEFEB', '#9CCFC5', '#367D72', '#075E55']
    for i, (count, sev) in enumerate(zip(counts, priorities)):
        x = 226+i*141
        s.rect(x, 177, 129, 36, COLORS[sev], CONTROL if not count else None, 2)
        s.text(x+64, 201, f'{LETTERS[sev]}  {count}' if count else '0', 14, '#FFFFFF' if count else MUTED, 650, 'middle')
        band = min(3, max(0, math.ceil(math.log1p(count)/math.log1p(96)*4)-1)) if count else -1
        s.rect(x, 235, 129, 36, ramp[band] if count else COLORS[0], CONTROL, 2)
        s.text(x+64, 259, count, 14, '#FFFFFF' if band >= 2 else INK, 650, 'middle')
    s.text(226, 295, 'Severity: maximum priority + separate count.', 13, MUTED)
    s.text(840, 295, 'Volume: 1–2 / 3–8 / 9–29 / 30–96 · relative to range.', 13, MUTED)
    s.text(24, 359, 'Coverage is not severity', 18, INK, 650)
    cards = [
        ('Complete zero', '0', '#F0F3F6', 'No anomaly in a complete bin.', 'Does not certify system health.'),
        ('Missing data', '!', 'url(#missing)', 'Known unavailable interval.', 'Never reported as complete zero.'),
        ('Unknown coverage', '?', '#F0F3F6', 'Completeness not supplied.', 'Observed counts may be incomplete.'),
        ('Partial coverage', 'H  3', COLORS[3], '3 observed anomalies; coverage partial.', 'No invented coverage percentage.'),
    ]
    for i, (title, label, color, a, b) in enumerate(cards):
        x = 24+i*352
        s.rect(x, 379, 336, 157, '#FFFFFF', LINE, 4)
        s.text(x+16, 407, title, 16, INK, 600)
        s.rect(x+16, 426, 84, 34, color, CONTROL, 2)
        if i == 3:
            s.rect(x+80, 426, 20, 16, 'url(#missing)')
        if i == 1:
            s.rect(x+47, 429, 22, 27, '#FFFFFF', CONTROL, 2)
        s.text(x+58, 449, label, 14, '#FFFFFF' if i == 3 else INK, 700, 'middle')
        s.text(x+16, 490, a, 13, MUTED)
        s.text(x+16, 513, b, 13, MUTED)
    s.text(24, 581, 'Requests retain a trustworthy scope', 18, INK, 650)
    s.rect(24, 602, 684, 153, '#FFFFFF', LINE, 4)
    s.text(44, 633, 'Updating', 16, INK, 650)
    s.text(44, 663, 'Applied: Synthetic fixture · all priorities', 14, INK)
    s.text(44, 689, 'Pending: Critical · updating timeline and results…', 14, TEAL, 600)
    s.text(44, 731, 'Existing data stays legible. Export is temporarily disabled.', 13, MUTED)
    s.rect(732, 602, 684, 153, '#FFFFFF', LINE, 4)
    s.text(752, 633, 'Update failed — previous results retained', 16, COLORS[3], 650)
    s.text(752, 663, 'Showing: Synthetic fixture · all priorities', 14, INK)
    s.text(752, 689, 'Your requested Critical filter has not been applied.', 14, MUTED)
    s.button(752, 705, 92, 'Retry')
    s.button(856, 705, 132, 'Revert draft')
    s.rect(24, 779, 684, 150, '#FFFFFF', LINE, 4)
    s.text(44, 810, 'No filter matches', 16, INK, 650)
    s.text(44, 840, 'No anomalies match the selected host and time range.', 14, MUTED)
    s.button(44, 867, 150, 'Clear selection')
    s.button(206, 867, 132, 'Clear filters')
    s.rect(732, 779, 684, 150, '#FFFFFF', LINE, 4)
    s.text(752, 810, 'No detection results', 16, INK, 650)
    s.text(752, 840, 'A source may contain logs without completed detector output.', 14, MUTED)
    s.text(752, 881, 'Show an explicit state; never substitute “0 anomalies”.', 14, INK, 600)
    s.rect(24, 955, 1392, 48, '#F5F7F9')
    s.text(44, 985, 'Selected = blue bracket + text; focus = separate dark outline. Pattern/symbol/text always supplement color.', 14, INK)
    s.save('timeline-v2-states')


def luminance(color):
    values = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(v*w for v, w in zip(linear, [.2126, .7152, .0722]))


def contrast(a, b):
    lo, hi = sorted([luminance(a), luminance(b)])
    return (hi+.05)/(lo+.05)


if __name__ == '__main__':
    workspace(1440).save('timeline-v2-desktop')
    workspace(1024).save('timeline-v2-compact')
    workspace(1440, selected=True).save('timeline-v2-selection')
    evidence()
    states()
    pairs = [(INK, '#FFFFFF'), (MUTED, '#FFFFFF'), (MUTED, '#F5F7F9'), ('#FFFFFF', TEAL), (BLUE, '#EDF3FF')]
    pairs += [('#FFFFFF', COLORS[p]) for p in range(1, 5)]
    pairs += [(INK, '#DCEFEB'), (INK, '#9CCFC5'), ('#FFFFFF', '#367D72'), ('#FFFFFF', '#075E55')]
    pairs += [(CONTROL, '#FFFFFF'), (BLUE, '#FFFFFF')]
    report = [{'foreground': a, 'background': b, 'ratio': round(contrast(a, b), 3)} for a, b in pairs]
    (ROOT/'token-contrast.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('Generated 5 SVG design sheets and token contrast measurements.')
