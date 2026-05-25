import sys, re; from pathlib import Path
sys.path.insert(0, r'H:\myprojects\genshin_qianxing_editor')
from tools.live_sync.gia_viz import extract_graph, parse_pins, node_label, get_catalog
from tools.live_sync.gia_utils import PIN_KIND_IN_FLOW, PIN_KIND_OUT_FLOW, PIN_KIND_IN_PARAM, PIN_KIND_OUT_PARAM

gia = Path(r'H:\myprojects\genshin_qianxing_editor\tools\live_sync\samples\export_examples\示例关卡资产.gia')
graphs = extract_graph(gia)
cat = get_catalog()

def _is_var_arity_extension(name, catalog_names):
    """检查是否是可变参数扩展名（如 元素1  ← 元素, 控制表达式1 ← 控制表达式）"""
    # 去掉末尾数字得到基名
    base = re.sub(r'\d+$', '', name)
    return base and base != name and base in catalog_names

for gi, g in enumerate(graphs):
    print(f'\n[{gi+1}] {g["name"]}')
    for nd in g['nodes']:
        nid = nd.get('1','?')
        lb = node_label(nd)
        pins = parse_pins(nd)
        ti = nd.get('2',{})
        tid = ti.get('5') if isinstance(ti,dict) else None
        ndef = cat.get_by_id(tid) if tid else None
        print(f'  N{nid} {lb}')
        if ndef:
            ci = {p.name for p in ndef.inputs}
            co = {p.name for p in ndef.outputs}
            for p in pins:
                m = ' [V]' if p.get('pin_index',-1)<0 else ''
                n = p['kind_name']
                d = 'I' if p['is_input'] else 'O'
                v = f'={p["param"]}' if p.get('param') is not None else ''
                c = f'>>{p["target_id"]}' if p.get('target_id') else ''
                k = ['?','IF','OF','ID','OD'][p['kind']] if 1<=p['kind']<=4 else f'K{p["kind"]}'
                w = ''
                # 仅对标准 kind (3=data_in, 4=data_out) 检查名称
                if p['kind'] in (3,4) and not m:
                    # 名称不在 catalog 中，且不是可变参数扩展 → !NAME
                    if n not in ci|co and not _is_var_arity_extension(n, ci|co):
                        w=' !NAME'
                if p['is_input'] and p['kind']==3 and p.get('param') is None and not p.get('target_id'):
                    w+=' !NOVAL'
                print(f'    {d} {n:24s}({k:3}){v}{c}{m}{w}')
        else:
            print(f'    !!NODEF')
print('\nDONE')
