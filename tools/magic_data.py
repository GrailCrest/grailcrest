"""Magic: The Gathering card data for GrailCrest, from MTGJSON (https://mtgjson.com, MIT license).

Builds small files GrailCrest reads to recognize a Magic card from its scan and show its price:
  magic/meta.json        when it was built and from which MTGJSON version
  magic/sets.json        every paper set: code -> [name, release date, base set size, total set size, type]
  magic/s/<CODE>.json    a set's cards: [number, name, rarity, finishes, tcgplayer, tcgplayer foil, card kingdom,
                         card kingdom foil, face name, language]
  magic/n/<ab>.json      names starting with those two letters -> [name, [[set code, number], ...]], newest first
Prices are today's retail prices in US dollars (TCGplayer market and Card Kingdom), as MTGJSON has them.

  python3 magic_data.py <out dir> [AllPrintings.json.xz] [AllPricesToday.json.gz]   (downloads them when not given)
"""
import gzip, json, lzma, os, re, sys, unicodedata, urllib.request
import ijson

MTGJSON = 'https://mtgjson.com/api/v5/'
RAR = {'common': 'C', 'uncommon': 'U', 'rare': 'R', 'mythic': 'M', 'special': 'S', 'bonus': 'B'}
LANG = {'English': '', 'Japanese': 'ja', 'German': 'de', 'French': 'fr', 'Italian': 'it', 'Spanish': 'es', 'Portuguese (Brazil)': 'pt',
        'Russian': 'ru', 'Korean': 'ko', 'Chinese Simplified': 'zhs', 'Chinese Traditional': 'zht', 'Phyrexian': 'ph'}


def norm(s):
    s = unicodedata.normalize('NFD', s or '')
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in s if not unicodedata.combining(c)).lower())


def fetch(name, dest):
    if not os.path.exists(dest):
        print('downloading', name, flush=True)
        with urllib.request.urlopen(urllib.request.Request(MTGJSON + name, headers={'User-Agent': 'GrailCrest magic data (https://grailcrest.app)'}), timeout=600) as r, open(dest, 'wb') as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
    return dest


def one(d):
    # {"2026-11-05": 1.23} -> 1.23
    if not d:
        return None
    v = list(d.values())[-1]
    return round(float(v), 2) if v is not None and float(v) > 0 else None


def main():
    out = sys.argv[1]
    printings = sys.argv[2] if len(sys.argv) > 2 else fetch('AllPrintings.json.xz', os.path.join(out, '..', 'AllPrintings.json.xz'))
    prices_f = sys.argv[3] if len(sys.argv) > 3 else fetch('AllPricesToday.json.gz', os.path.join(out, '..', 'AllPricesToday.json.gz'))
    pr = json.load(gzip.open(prices_f))
    prices, version = pr['data'], pr['meta']
    print('prices for', len(prices), 'cards,', version, flush=True)

    os.makedirs(os.path.join(out, 'magic', 's'), exist_ok=True)
    os.makedirs(os.path.join(out, 'magic', 'n'), exist_ok=True)
    sets, names, ncards, pmeta = {}, {}, 0, None
    with lzma.open(printings, 'rb') as f:
        for code, s in ijson.kvitems(f, 'data', use_float=True):
            if s.get('isOnlineOnly') or not s.get('cards'):
                continue
            rows = []
            for c in s['cards']:
                if 'paper' not in (c.get('availability') or []) or c.get('isOnlineOnly'):
                    continue
                if c.get('side') and c['side'] != 'a':      # the other faces of a double-faced card: the same printing
                    continue
                p = ((prices.get(c['uuid']) or {}).get('paper') or {})
                tcg = ((p.get('tcgplayer') or {}).get('retail') or {})
                ck = ((p.get('cardkingdom') or {}).get('retail') or {})
                fin = ''.join(x[0] for x in (c.get('finishes') or []) if x in ('nonfoil', 'foil', 'etched'))
                face = c.get('faceName') if c.get('faceName') and c.get('faceName') != c['name'] else ''
                lang = LANG.get(c.get('language') or 'English', (c.get('language') or '')[:3].lower())
                rows.append([c['number'], c['name'], RAR.get(c.get('rarity'), (c.get('rarity') or '?')[:1].upper()), fin,
                             one(tcg.get('normal')), one(tcg.get('foil') or tcg.get('etched')), one(ck.get('normal')), one(ck.get('foil') or ck.get('etched')), face, lang])
            if not rows:
                continue
            ncards += len(rows)
            sets[code] = [s['name'], s.get('releaseDate') or '', s.get('baseSetSize') or 0, s.get('totalSetSize') or 0, s.get('type') or '']
            with open(os.path.join(out, 'magic', 's', code + '.json'), 'w') as g:
                json.dump({'code': code, 'name': s['name'], 'date': s.get('releaseDate') or '', 'c': rows}, g, separators=(',', ':'))
            for r in rows:
                for nm in {r[1], r[8]} - {''}:
                    k = norm(nm)
                    if len(k) < 2:
                        k = (k + '__')[:2] if k else '__'
                    e = names.setdefault(k, [nm, []])
                    e[1].append([code, r[0]])
    # newest printings first
    date = {c: v[1] for c, v in sets.items()}
    shards = {}
    for k, (nm, ps) in names.items():
        ps.sort(key=lambda x: date.get(x[0], ''), reverse=True)
        shards.setdefault(k[:2], {})[k] = [nm, ps]
    for k, d in shards.items():
        with open(os.path.join(out, 'magic', 'n', k + '.json'), 'w') as g:
            json.dump(d, g, separators=(',', ':'), ensure_ascii=False)
    with open(os.path.join(out, 'magic', 'sets.json'), 'w') as g:
        json.dump(sets, g, separators=(',', ':'), ensure_ascii=False)
    with open(os.path.join(out, 'magic', 'meta.json'), 'w') as g:
        json.dump({'built': version.get('date'), 'mtgjson': version.get('version'), 'sets': len(sets), 'cards': ncards, 'names': len(names),
                   'source': 'MTGJSON (https://mtgjson.com), MIT license, Copyright (c) 2018-Present Zach Halpern. Prices: TCGplayer market and Card Kingdom retail, USD.'}, g, indent=1)
    with open(os.path.join(out, 'LICENSE-MTGJSON.txt'), 'w') as g:
        g.write(MIT)
    with open(os.path.join(out, 'README.md'), 'w') as g:
        g.write('# GrailCrest Magic card data\n\nBuilt every day from [MTGJSON](https://mtgjson.com) by `tools/magic_data.py` on the main branch. '
                'MTGJSON is MIT licensed (see LICENSE-MTGJSON.txt). Magic: The Gathering is a trademark of Wizards of the Coast LLC; '
                'GrailCrest is not affiliated with or endorsed by Wizards of the Coast.\n')
    print('sets', len(sets), 'cards', ncards, 'names', len(names), 'name files', len(shards), flush=True)


MIT = """MIT License

Copyright (c) 2018 - Present, Zach Halpern

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

if __name__ == '__main__':
    main()
