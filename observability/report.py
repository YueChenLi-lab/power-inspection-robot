"""Dependency-free standalone SVG charts generated only from actual records."""
from html import escape
from observability.metrics import distribution


def bars(path,title,rows):
    max_value=max((v for _,v in rows),default=1) or 1
    height=90+len(rows)*32
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}">',
           '<rect width="100%" height="100%" fill="white"/>',f'<text x="20" y="30" font-size="18">{escape(title)}</text>']
    for i,(label,v) in enumerate(rows):
        y=60+i*32
        parts.extend([f'<text x="20" y="{y+14}" font-size="12">{escape(label)}</text>',
                      f'<rect x="350" y="{y}" width="{v/max_value*450:.2f}" height="20" fill="#3576ad"/>',
                      f'<text x="810" y="{y+14}" font-size="12">{v:.6f}</text>'])
    path.write_text('\n'.join(parts+['</svg>']))


def charts(report,folder):
    rows=[]
    for r in report['runs']:
        m=r['metrics']['mission_latency_seconds']
        for p in ('p50','p95','p99'):rows.append((f'c={r["concurrency"]}, latency={r["network_latency"]} {p}',m[p] or 0))
    bars(folder/'latency-percentiles.svg','Mock mission latency percentiles (seconds)',rows)
    bars(folder/'concurrency.svg','Request concurrency vs mean task response (seconds)',
         [(f'concurrency={r["concurrency"]}',r['metrics']['mission_latency_seconds']['mean']) for r in report['runs'] if r['network_latency']==0])
    phases=[]
    for name in ('queue_seconds','skill_seconds','storage_write_seconds','network_seconds'):
        for p in ('p50','p95','p99'):
            phases.append((name+' '+p,report['runs'][0]['metrics'][name][p] or 0))
    for stage in ('schema','evidence_semantic_validator','semantic_total'):
        d=distribution([s['seconds'] for s in report['semantic_spans'] if s['stage']==stage])
        for p in ('p50','p95','p99'):phases.append((stage+' '+p,d[p] or 0))
    bars(folder/'stage-distributions.svg','Measured stage distributions (seconds, inclusive semantic validation)',phases)
    bars(folder/'provider-comparison.svg','Mock/Rules total semantic response latency (seconds); real Qwen unmeasured',
         [(r['provider']+' '+p,r['summary']['latency_seconds'][p]) for r in report['model_comparison'] for p in ('p50','p95','p99')])
    bars(folder/'network-recovery.svg','Mock task completions before and after network recovery (counts)',
         [(f'c={r["concurrency"]} latency={r["network_latency"]} {phase}',r[phase].get('SUCCEEDED',0)) for r in report['runs'] for phase in ('before_recovery','after_recovery')])
