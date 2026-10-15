"""Keep final artwork free of documentation; retain metadata for traceability."""
import copy
if __package__:
    from .validation import parse_svg
else:
    from validation import parse_svg
import xml.etree.ElementTree as ET


def uniform_background_outline(root):
    """Stroke after tissue fills so no part of the same edge is half-covered."""
    backgrounds={'source-derived-background','allen-reconstructed-background','stylized-cerebellar-lobules'}
    for group in root.iter():
        if group.get('id') not in backgrounds:continue
        candidates=[p for p in group if p.tag.split('}')[-1]=='path' and
                    (p.get('data-role')=='brain-outline' or (p.get('stroke','none')!='none' and p.get('fill','none')!='none'))]
        if not candidates:continue
        outline=copy.deepcopy(candidates[0]);outline.set('fill','none');outline.set('data-role','brain-outline')
        outline.set('stroke-linejoin','round');outline.set('stroke-linecap','round')
        for p in candidates:
            if p.get('data-role')=='brain-outline':group.remove(p)
            else:p.set('stroke','none');p.attrib.pop('stroke-width',None)
        # The cerebellum is a foreground structure; do not redraw the hidden
        # cerebral/brainstem edge across its interior.
        cb=next((p for p in group if p.get('id')=='stylized-cerebellar-lobules'),None)
        if cb is not None:group.insert(list(group).index(cb),outline)
        else:group.append(outline)
    return root


def diagram_only(svg, labels, height=None):
    root=uniform_background_outline(parse_svg(svg))
    keep=set(labels)
    for parent in list(root.iter()):
        for child in list(parent):
            tag=child.tag.split('}')[-1]
            if child.get('id')=='figure-annotations' or (tag=='text' and ''.join(child.itertext()).strip() not in keep):
                parent.remove(child)
    if height is not None:
        view=root.get('viewBox').split()
        view[3]=str(height);root.set('viewBox',' '.join(view));root.set('height',str(height))
    ET.register_namespace('','http://www.w3.org/2000/svg')
    return ET.tostring(root,encoding='unicode')
