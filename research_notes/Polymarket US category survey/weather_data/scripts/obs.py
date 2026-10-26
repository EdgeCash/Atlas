import csv, re, datetime as dt, json, collections
LST = {'KNYC':-5,'KMIA':-5,'KPHL':-5,'KMDW':-6,'KORD':-6,'KLAX':-8,'KSFO':-8}
FILE = {'KNYC':'NYC','KMIA':'MIA','KPHL':'PHL','KMDW':'MDW','KORD':'ORD','KLAX':'LAX','KSFO':'SFO'}
def c2f(c): return c * 9 / 5 + 32
def parse(station):
    out = []
    for r in csv.DictReader(open(f'raw/asos/{FILE[station]}.csv')):
        t = dt.datetime.strptime(r['valid'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.timezone.utc)
        m = r['metar']; rmk = m.split(' RMK ')[1] if ' RMK ' in m else ''
        tf = None
        g = re.search(r'\bT([01])(\d{3})([01])(\d{3})\b', rmk)
        if g: tf = round(c2f((-1 if g[1] == '1' else 1) * int(g[2]) / 10))
        elif r['tmpf'] not in ('M', ''): tf = round(float(r['tmpf']))
        mx6 = mn6 = None
        g = re.search(r'(?:^|\s)1([01])(\d{3})(?=\s|$)', rmk)
        if g: mx6 = round(c2f((-1 if g[1] == '1' else 1) * int(g[2]) / 10))
        g = re.search(r'(?:^|\s)2([01])(\d{3})(?=\s|$)', rmk)
        if g: mn6 = round(c2f((-1 if g[1] == '1' else 1) * int(g[2]) / 10))
        mx24 = mn24 = None
        g = re.search(r'(?:^|\s)4([01])(\d{3})([01])(\d{3})(?=\s|$)', rmk)
        if g:
            mx24 = round(c2f((-1 if g[1] == '1' else 1) * int(g[2]) / 10)); mn24 = round(c2f((-1 if g[3] == '1' else 1) * int(g[4]) / 10))
        out.append(dict(t=t, lst=t + dt.timedelta(hours=LST[station]), tf=tf, mx6=mx6, mn6=mn6, mx24=mx24, mn24=mn24, wx=r['wxcodes'], metar=m))
    return out
