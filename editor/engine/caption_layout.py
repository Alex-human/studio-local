"""Measured layout for the editable words of the Editorial morado preset."""
import math
import graphics

LAYOUT = dict(name='Editorial morado', version=1, width=1080, height=1920,
              videoX=44, videoY=681, videoWidth=992, videoHeight=558,
              hookX=540, hookY=562.5, hookSize=60.75,
              captionX=540, captionY=1320, captionSize=72,
              safeWidth=880, lineHeight=88, accent='#B28CFF')
DESIGN_SCALE = 1920 / LAYOUT['width']
LAYOUT_FIELDS = ('text', 'size', 'weight', 'x', 'y', 'style', 'subtitle')


def word_positions(props):
    """Measure the complete phrase, including words which have not entered yet."""
    faces = [graphics.font(p.get('size', 128) / DESIGN_SCALE, p.get('weight', 700)) for p in props]
    widths = [face.getlength(p['text']) for face, p in zip(faces, props)]
    visible = [i for i, p in enumerate(props) if p['text'].strip()]
    def gap(left, right):
        return (faces[left].getlength(' ') + faces[right].getlength(' ')) / 2
    def line_width(line):
        return sum(widths[i] for i in line) + sum(gap(a, b) for a, b in zip(line, line[1:]))
    lines = [visible]
    if line_width(visible) > LAYOUT['safeWidth']:
        splits = [i for i in range(1, len(visible))
                  if max(line_width(visible[:i]), line_width(visible[i:])) <= LAYOUT['safeWidth']]
        if not splits:
            raise ValueError('El subtítulo no cabe en dos líneas; acorta el texto o reduce su tamaño')
        middle = min(splits, key=lambda i: abs(line_width(visible[:i]) - line_width(visible[i:])))
        lines = [visible[:middle], visible[middle:]]
    positions = [(LAYOUT['captionX'], LAYOUT['captionY'])] * len(props)
    line_height = max([LAYOUT['lineHeight']] + [p.get('size', 128) / DESIGN_SCALE * 88 / 72 for p in props])
    for row, line in enumerate(lines):
        x = LAYOUT['captionX'] - line_width(line) / 2
        for at, index in enumerate(line):
            positions[index] = (x + widths[index] / 2, LAYOUT['captionY'] + row * line_height)
            x += widths[index] + (gap(index, line[at+1]) if at+1 < len(line) else 0)
    return [(x * DESIGN_SCALE, y * DESIGN_SCALE) for x, y in positions]


def legacy_word(p, item):
    props = item.get('props', {})
    return ((p['width'], p['height']) == (1080, 1920)
            and item.get('type') == 'title' and not item.get('captionGroup')
            and props.get('style', 'plain') == 'plain' and not props.get('subtitle')
            and not item.get('keepTogether') and set(item.get('keyframes', {})) <= {'opacity'}
            and props.get('size') == 128 and props.get('weight') == 700
            and props.get('enter') == .01 and props.get('accent') == LAYOUT['accent']
            and item.get('offset', 0) >= math.ceil(p['fps'] * .25)
            and any(math.isclose(props.get('y', 0), y * DESIGN_SCALE, abs_tol=.001)
                    for y in (1320, 1408)))


def edit_group(p, item, values):
    """Use pre-edit identity; never infer a group from the replacement word."""
    before, after = item.get('props', {}), values.get('props', {})
    if not any(key in after and before.get(key) != after[key] for key in ('text', 'size', 'weight')):
        return []
    if item.get('type') != 'title' or before.get('style', 'plain') != 'plain':
        return []
    token = item.get('captionGroup')
    if not token and not legacy_word(p, item):
        return []
    end = item['start'] + item['length']
    members = [g for g in p['graphics'] if g['start'] + g['length'] == end
               and (g.get('captionGroup') == token if token else legacy_word(p, g))]
    key = lambda g: g['captionIndex'] if token else (g['props']['y'], g['props']['x'])
    members.sort(key=key)
    # A duplicate occupying the same slot is an independent, ambiguous title.
    if len({key(g) for g in members}) != len(members):
        return []
    return members


def reflow(members):
    token = members[0].get('captionGroup') or min(g['id'] for g in members)
    for member in members:
        member['props']['text'] = ' '.join(member['props']['text'].split())
    positions = word_positions([g['props'] for g in members])
    for index, (member, (x, y)) in enumerate(zip(members, positions)):
        member.update(captionGroup=token, captionIndex=index)
        member['props'].update(x=x, y=y)


def unchanged_group(base_members, current):
    """Derived coordinates must never merge from competing layouts."""
    for before in base_members:
        after = next((g for g in current['graphics'] if g['id'] == before['id']), None)
        if after is None or any(before.get(k) != after.get(k) for k in ('start', 'length', 'captionGroup', 'captionIndex')):
            return False
        if any(before['props'].get(k) != after.get('props', {}).get(k) for k in LAYOUT_FIELDS):
            return False
    return True
