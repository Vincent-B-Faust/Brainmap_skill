"""Shared finite-number and passive-vector boundaries for rendering APIs."""
import json
import re
import xml.etree.ElementTree as ET

import numpy as np

SVG_NS = 'http://www.w3.org/2000/svg'
XLINK_NS = 'http://www.w3.org/1999/xlink'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
TAGS = set('svg g path rect circle ellipse line polyline polygon defs clipPath mask linearGradient radialGradient stop marker text tspan title desc metadata style'.split())
METADATA_TAGS = set('caption creationDate creator credit description illustrationSoftwares imageColor license title isDiscoverThumbnail'.split())
ATTRS = set('id class style version viewBox preserveAspectRatio x y x1 y1 x2 y2 cx cy r rx ry width height d points transform fill fill-rule fill-opacity stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset opacity clip-path clip-rule clipPathUnits mask maskUnits maskContentUnits gradientUnits gradientTransform spreadMethod offset stop-color stop-opacity fx fy fr font-family font-size font-weight font-style text-anchor dominant-baseline dx dy rotate lengthAdjust textLength display visibility color isolation mix-blend-mode markerWidth markerHeight markerUnits refX refY orient marker-start marker-mid marker-end structure_id graphic_group_label graphic_group_label_id order parent_id sub_image_id'.split())
CSS_PROPERTIES = set('marker-start marker-mid marker-end fill fill-rule fill-opacity stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset opacity clip-path clip-rule mask stop-color stop-opacity font-family font-size font-weight font-style text-anchor dominant-baseline display visibility color isolation mix-blend-mode'.split())
LOCAL_URL = re.compile(r'url\(\s*[\'"]?#[A-Za-z_][\w.:-]*[\'"]?\s*\)', re.I)


def finite_json(value):
    """Reject Python JSON extensions such as NaN and Infinity at API boundaries."""
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError('Input must be JSON with finite numbers') from error


def finite_array(value, name, shape=None):
    try:
        result = np.asarray(value, dtype=float)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f'{name} must contain finite numbers') from error
    if not np.isfinite(result).all() or (shape is not None and result.shape != shape):
        raise ValueError(f'{name} must be finite with shape {shape}')
    return result


def _static_value(value):
    # Conservative CSS subset: no escapes, comments, directives or functions
    # that can fetch content. Only fragment URLs in the same SVG are supported.
    if any(c in value for c in ('\\', '/*', '*/', '@', '<', '>')):
        raise ValueError('Unsupported SVG/CSS syntax')
    stripped = LOCAL_URL.sub('', value)
    if re.search(r'url\s*\(|(?:expression|javascript|vbscript)\s*[:(]', stripped, re.I):
        raise ValueError('External or active SVG/CSS value')


def _declarations(text):
    for item in text.split(';'):
        if not item.strip():
            continue
        if ':' not in item:
            raise ValueError('Invalid SVG style declaration')
        key, value = item.split(':', 1)
        if key.strip().lower() not in CSS_PROPERTIES:
            raise ValueError('Unsupported SVG style property')
        _static_value(value)


def validate_svg(root, native=False):
    """Allow static SVG graphics; reject rather than repair untrusted content."""
    if root.tag not in ('svg', '{'+SVG_NS+'}svg'):
        raise ValueError('Source is not SVG')
    allowed = {'svg', 'g', 'path', 'metadata', 'title', 'desc'} if native else TAGS

    def visit(element, in_metadata=False):
        tag = element.tag
        namespace, local = (tag[1:].split('}', 1) if tag.startswith('{') else ('', tag))
        metadata_field = in_metadata and namespace in ('', SVG_NS) and local in METADATA_TAGS
        if namespace not in ('', SVG_NS) or (local not in allowed and not metadata_field):
            raise ValueError('Unsupported SVG element or namespace')
        for key, value in element.attrib.items():
            ns, name = (key[1:].split('}', 1) if key.startswith('{') else ('', key))
            if name.lower().startswith('on'):
                raise ValueError('SVG event attributes are not supported')
            if name == 'href' and ns in ('', XLINK_NS):
                if native or not re.fullmatch(r'#[A-Za-z_][\w.:-]*', value):
                    raise ValueError('Only local SVG references are supported')
            elif ns == XML_NS and name in ('lang', 'space'):
                pass
            elif ns or (name not in ATTRS and not name.startswith('data-')):
                raise ValueError('Unsupported SVG attribute or namespace')
            if name == 'style':
                _declarations(value)
            else:
                _static_value(value)
        if local == 'style':
            text = element.text or ''
            _static_value(text)
            pos = 0
            for rule in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
                if text[pos:rule.start()].strip():
                    raise ValueError('Unsupported SVG stylesheet')
                selectors = rule[1].split(',')
                if any(not re.fullmatch(r'\s*(?:[.#]?[A-Za-z_][\w-]*)\s*', s) for s in selectors):
                    raise ValueError('Unsupported SVG CSS selector')
                _declarations(rule[2]);pos = rule.end()
            if text[pos:].strip():
                raise ValueError('Unsupported SVG stylesheet')
        for child in element:
            visit(child, in_metadata or local == 'metadata')
    visit(root)
    return root


def parse_svg(text, native=False):
    if isinstance(text, bytes):
        text = text.decode('utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)|<\?', text.replace('<?xml ', '<xml ', 1), re.I):
        raise ValueError('SVG declarations and processing instructions are unsupported')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError('Invalid SVG XML') from error
    return validate_svg(root, native)
